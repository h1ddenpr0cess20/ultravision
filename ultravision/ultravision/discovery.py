"""Auto-discovery for LM Studio/Ollama vision model servers."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import struct
from typing import Dict, Iterator, List, Optional, Set, Tuple

import aiohttp

try:
    import psutil
except Exception:
    psutil = None

DEFAULT_VISION_MODEL_HINTS = ("gemma3",)
DOCKER_HOST_ALIASES = ("host.docker.internal",)
DOCKER_CONTAINER_MARKERS = ("docker", "kubepods", "containerd")
MAX_NETWORK_SCAN_HOSTS = 512


class VisionModelDiscovery:
    """Discovery service for vision models on LM Studio and Ollama servers."""

    def __init__(
        self,
        lm_studio_port: int = 1234,
        ollama_port: int = 11434,
        timeout: float = 2.0,
        additional_vision_models: Optional[List[str]] = None,
    ) -> None:
        """Configure the discovery service.

        Args:
            lm_studio_port (int): Port probed for LM Studio servers.
            ollama_port (int): Port probed for Ollama servers.
            timeout (float): Total timeout for discovery HTTP calls, in seconds.
            additional_vision_models (Optional[List[str]]): Extra model-id
                substrings treated as vision-capable, force-including models a
                server doesn't advertise. Capability metadata is the primary
                signal; these are just an override hatch.
        """
        self.lm_studio_port = lm_studio_port
        self.ollama_port = ollama_port
        self.timeout = timeout
        self.additional_vision_models = [h.lower() for h in (additional_vision_models or [])]
        self._running_in_container = self._detect_container_environment()

    @staticmethod
    def _primary_local_ip() -> Optional[str]:
        """Best-effort primary IPv4 address via the outbound-socket trick.

        Opens a UDP socket toward a public address (no packets are actually
        sent) and reads back the local address the OS would route through.
        Works on every platform without psutil/netifaces, so LAN discovery
        keeps functioning even when richer enumeration is unavailable.
        """

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return None
        finally:
            sock.close()

    @classmethod
    def _iter_inet_addresses(cls) -> Iterator[Tuple[str, Optional[str]]]:
        """Yield ``(ip, netmask)`` for every usable IPv4 address on the host.

        Uses psutil for full per-interface detail when it is importable, and
        always includes the primary outbound IP (assuming a ``/24`` subnet) so
        discovery still scans the local network when psutil is missing or
        returns nothing useful.
        """

        seen_with_mask: Set[str] = set()
        if psutil is not None:
            try:
                interfaces = psutil.net_if_addrs()
            except Exception:
                interfaces = {}
            for addrs in interfaces.values():
                for addr in addrs:
                    if addr.family == socket.AF_INET and addr.address:
                        yield addr.address, addr.netmask
                        if addr.netmask:
                            seen_with_mask.add(addr.address)

        primary = cls._primary_local_ip()
        if primary and primary not in seen_with_mask and not primary.startswith("127."):
            yield primary, "255.255.255.0"

    def _get_local_addresses(self) -> Set[str]:
        """Return localhost aliases and interface IPs."""

        local_ips = {"127.0.0.1", "localhost"}
        for ip, _netmask in self._iter_inet_addresses():
            local_ips.add(ip)
        return local_ips

    def _get_default_gateways(self) -> Set[str]:
        """Return IPv4 gateway addresses (often the Docker host from containers).

        psutil does not expose routing information, so we parse Linux's
        ``/proc/net/route`` directly. On platforms without it (or when the file
        cannot be read) we simply return no gateways.
        """

        gateways: Set[str] = set()
        try:
            with open("/proc/net/route", "rt", encoding="utf-8") as handle:
                rows = handle.readlines()
        except OSError:
            return gateways

        for line in rows[1:]:
            fields = line.split()
            if len(fields) < 3:
                continue
            destination, gateway_hex = fields[1], fields[2]
            if destination != "00000000":
                continue
            try:
                gateway = socket.inet_ntoa(struct.pack("<L", int(gateway_hex, 16)))
            except (ValueError, struct.error, OSError):
                continue
            if gateway and gateway != "0.0.0.0":
                gateways.add(gateway)

        return gateways

    def _get_network_hosts(self) -> Set[str]:
        """Enumerate all potential LAN hosts excluding the known interface IPs."""

        local_ips = self._get_local_addresses()
        potential_hosts: Set[str] = set()
        gateway_hosts = self._get_default_gateways()
        for ip, netmask in self._iter_inet_addresses():
            if not ip or not netmask or ip.startswith("127."):
                continue
            try:
                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
            except Exception:
                continue
            host_limit = (
                MAX_NETWORK_SCAN_HOSTS if network.num_addresses > MAX_NETWORK_SCAN_HOSTS + 2 else None
            )
            count = 0
            try:
                for host in network.hosts():
                    host_str = str(host)
                    if host_str in local_ips:
                        continue
                    potential_hosts.add(host_str)
                    count += 1
                    if host_limit is not None and count >= host_limit:
                        break
            except Exception:
                continue
        potential_hosts.update(gateway_hosts - local_ips)
        return potential_hosts

    def _name_hinted(self, model_id: str) -> bool:
        """Return ``True`` if the id matches a caller-supplied vision hint."""

        lowered = model_id.lower()
        return any(needle in lowered for needle in self.additional_vision_models)

    async def _check_port(self, host: str, port: int) -> bool:
        """Quick async port probe."""

        if port <= 0:
            return False
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=0.3,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        method: str = "GET",
        payload: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """GET/POST ``url`` and return parsed JSON, or ``None`` on any failure."""

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout, connect=0.5)
            if method == "POST":
                ctx = session.post(url, json=payload, timeout=timeout)
            else:
                ctx = session.get(url, timeout=timeout)
            async with ctx as response:
                if response.status != 200:
                    return None
                return await response.json()
        except Exception:
            return None

    async def _fetch_models(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        service_type: Optional[str] = None,
    ) -> List[str]:
        """Return the candidate model ids for a reachable server.

        Vision capability is read from provider metadata so *any* vision model is
        detected regardless of its name: LM Studio's native ``/api/v0/models``
        exposes a ``type`` of ``vlm``, and Ollama's ``/api/show`` reports a
        ``capabilities`` list containing ``vision``. When that metadata is
        unavailable (older servers, plain OpenAI-compatible backends) we list
        every model from ``/v1/models`` rather than hide the server.
        """

        if service_type == "lm_studio":
            vlms = await self._fetch_lmstudio_vlms(session, base_url)
            if vlms is not None:
                return vlms
        elif service_type == "ollama":
            vision = await self._fetch_ollama_vision(session, base_url)
            if vision is not None:
                return vision
        return await self._fetch_all_models(session, base_url)

    async def _fetch_all_models(self, session: aiohttp.ClientSession, base_url: str) -> List[str]:
        """List every model id from the OpenAI-compatible ``/v1/models`` endpoint."""

        payload = await self._get_json(session, f"{base_url}/v1/models")
        if not payload:
            return []
        entries = payload.get("data") or payload.get("models")
        if not isinstance(entries, list):
            return []
        return [row.get("id", "") for row in entries if isinstance(row, dict) and row.get("id")]

    async def _fetch_lmstudio_vlms(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> Optional[List[str]]:
        """Vision models from LM Studio's native API (``type == 'vlm'``).

        Returns ``None`` when the native endpoint is unavailable so the caller
        falls back to listing all models.
        """

        payload = await self._get_json(session, f"{base_url}/api/v0/models")
        if not payload:
            return None
        entries = payload.get("data") or payload.get("models")
        if not isinstance(entries, list):
            return None
        models = []
        for row in entries:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id", "")
            if not model_id:
                continue
            if str(row.get("type", "")).lower() == "vlm" or self._name_hinted(model_id):
                models.append(model_id)
        return models

    async def _fetch_ollama_vision(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> Optional[List[str]]:
        """Vision models from Ollama via ``/api/tags`` + ``/api/show`` capabilities.

        Returns ``None`` when ``/api/tags`` is unavailable. If the server is too
        old to report capabilities at all, every tag is returned rather than
        dropping the server.
        """

        tags = await self._get_json(session, f"{base_url}/api/tags")
        if not tags:
            return None
        rows = tags.get("models")
        if not isinstance(rows, list):
            return None
        names = [
            (row.get("model") or row.get("name"))
            for row in rows
            if isinstance(row, dict) and (row.get("model") or row.get("name"))
        ]
        if not names:
            return []

        async def _capabilities(name: str) -> Tuple[str, Optional[List[str]]]:
            info = await self._get_json(
                session, f"{base_url}/api/show", method="POST", payload={"model": name}
            )
            caps = (info or {}).get("capabilities")
            return name, caps if isinstance(caps, list) else None

        results = await asyncio.gather(
            *(_capabilities(name) for name in names), return_exceptions=True
        )
        vision: List[str] = []
        saw_capabilities = False
        for result in results:
            if not isinstance(result, tuple):
                continue
            name, caps = result
            if caps is not None:
                saw_capabilities = True
                if "vision" in caps or self._name_hinted(name):
                    vision.append(name)
            elif self._name_hinted(name):
                vision.append(name)
        return vision if saw_capabilities else names

    async def _discover_localhost(self, session: aiohttp.ClientSession) -> Dict[str, Optional[Dict]]:
        """Return ``lm_studio`` / ``ollama`` entries found on localhost."""

        local_ips = self._get_local_addresses()
        results: Dict[str, Optional[Dict]] = {"lm_studio": None, "ollama": None}

        if await self._check_port("127.0.0.1", self.lm_studio_port):
            models = await self._fetch_models(
                session, f"http://127.0.0.1:{self.lm_studio_port}", "lm_studio"
            )
            if models:
                results["lm_studio"] = {
                    "server_address": f"http://127.0.0.1:{self.lm_studio_port}",
                    "local_addresses": sorted(
                        f"http://{ip}:{self.lm_studio_port}" for ip in local_ips
                    ),
                    "vision_models": models,
                }

        if await self._check_port("127.0.0.1", self.ollama_port):
            models = await self._fetch_models(
                session, f"http://127.0.0.1:{self.ollama_port}", "ollama"
            )
            if models:
                results["ollama"] = {
                    "server_address": f"http://127.0.0.1:{self.ollama_port}",
                    "local_addresses": sorted(
                        f"http://{ip}:{self.ollama_port}" for ip in local_ips
                    ),
                    "vision_models": models,
                }

        if not results["lm_studio"]:
            alias_entry = await self._discover_host_alias(
                session, "lm_studio", self.lm_studio_port
            )
            if alias_entry:
                results["lm_studio"] = alias_entry

        if not results["ollama"]:
            alias_entry = await self._discover_host_alias(
                session, "ollama", self.ollama_port
            )
            if alias_entry:
                results["ollama"] = alias_entry

        return results

    def _detect_container_environment(self) -> bool:
        """Detect whether the discovery helper is running inside a container."""

        forced = os.environ.get("ULTRAVISION_INSIDE_DOCKER")
        if forced:
            return forced.strip().lower() in {"1", "true", "yes"}
        if os.path.exists("/.dockerenv"):
            return True
        try:
            with open("/proc/1/cgroup", "rt", encoding="utf-8") as handle:
                contents = handle.read()
        except OSError:
            return False
        return any(marker in contents for marker in DOCKER_CONTAINER_MARKERS)

    async def _discover_host_alias(
        self, session: aiohttp.ClientSession, service_type: str, port: int
    ) -> Optional[Dict]:
        """Check well-known Docker host aliases when localhost lookup fails."""

        if port <= 0:
            return None
        if not self._running_in_container:
            return None
        for alias in DOCKER_HOST_ALIASES:
            if not await self._check_port(alias, port):
                continue
            _, info = await self._fetch_server_info(
                session, service_type, f"http://{alias}:{port}"
            )
            if info:
                return info
        return None

    async def _check_port_and_service(
        self, host: str, service_type: str, port: int
    ) -> Tuple[str, str, bool]:
        """Probe a host/port tuple and tag it with the service type."""

        is_open = await self._check_port(host, port)
        return (service_type, host, is_open)

    async def _fetch_server_info(
        self, session: aiohttp.ClientSession, service_type: str, url: str
    ) -> Tuple[str, Optional[Dict]]:
        """Return structured info for a reachable server."""

        models = await self._fetch_models(session, url, service_type)
        if models:
            return (
                service_type,
                {
                    "server_address": url,
                    "vision_models": models,
                },
            )
        return (service_type, None)

    async def _discover_network(self, session: aiohttp.ClientSession) -> Dict[str, List[Dict]]:
        """Scan the LAN for LM Studio or Ollama instances."""

        potential_hosts = self._get_network_hosts()
        results: Dict[str, List[Dict]] = {"lm_studio": [], "ollama": []}

        port_scan_tasks = []
        for host in potential_hosts:
            port_scan_tasks.append(
                self._check_port_and_service(host, "lm_studio", self.lm_studio_port)
            )
            port_scan_tasks.append(
                self._check_port_and_service(host, "ollama", self.ollama_port)
            )

        active_servers = {"lm_studio": set(), "ollama": set()}
        scan_results = await asyncio.gather(*port_scan_tasks, return_exceptions=True)
        for result in scan_results:
            if isinstance(result, tuple) and len(result) == 3 and result[2]:
                service_type, host, _open = result
                active_servers[service_type].add(host)

        model_fetch_tasks = []
        for host in active_servers["lm_studio"]:
            url = f"http://{host}:{self.lm_studio_port}"
            model_fetch_tasks.append(self._fetch_server_info(session, "lm_studio", url))
        for host in active_servers["ollama"]:
            url = f"http://{host}:{self.ollama_port}"
            model_fetch_tasks.append(self._fetch_server_info(session, "ollama", url))

        fetch_results = await asyncio.gather(*model_fetch_tasks, return_exceptions=True)
        for result in fetch_results:
            if isinstance(result, tuple) and result[1]:
                service_type, server_info = result
                results[service_type].append(server_info)

        return results

    async def discover(self) -> Dict[str, List[Dict]]:
        """Discover LM Studio/Ollama hosts with vision-capable models."""

        connector = aiohttp.TCPConnector(limit=30, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            localhost_results = await self._discover_localhost(session)
            network_results = await self._discover_network(session)

        results = {"lm_studio": [], "ollama": []}
        if localhost_results["lm_studio"]:
            results["lm_studio"].append(localhost_results["lm_studio"])
        if localhost_results["ollama"]:
            results["ollama"].append(localhost_results["ollama"])

        results["lm_studio"].extend(network_results["lm_studio"])
        results["ollama"].extend(network_results["ollama"])
        return results


__all__ = ["VisionModelDiscovery", "DEFAULT_VISION_MODEL_HINTS"]
