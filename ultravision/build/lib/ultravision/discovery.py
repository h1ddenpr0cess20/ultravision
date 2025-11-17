"""Discovery helpers to auto-detect LM Studio and Ollama servers on local networks."""

from __future__ import annotations

import asyncio
import ipaddress
import re
from typing import Dict, List, Optional, Set, Tuple

import aiohttp

try:  # Optional dependency for network interface enumeration
    import netifaces  # type: ignore
except Exception:  # pragma: no cover - only triggered when dependency missing
    netifaces = None  # type: ignore


class VisionModelDiscovery:
    """Find local LM Studio and Ollama servers plus the vision models they host."""

    def __init__(
        self,
        lm_studio_port: int = 1234,
        ollama_port: int = 11434,
        timeout: float = 2.0,
        additional_vision_models: Optional[List[str]] = None,
    ):
        """Initialize scanning defaults."""
        self.lm_studio_port = lm_studio_port
        self.ollama_port = ollama_port
        self.timeout = timeout
        self.additional_vision_models = additional_vision_models or []
        self.qwen_patterns = [
            re.compile(r"qwen\d+(\.\d+)?-?vl", re.IGNORECASE),
            re.compile(r"qwen/qwen\d+(\.\d+)?-?vl", re.IGNORECASE),
        ]

    def _get_local_addresses(self) -> Set[str]:
        """Return localhost aliases and interface IPs."""
        local_ips = {"127.0.0.1", "localhost"}
        if netifaces is None:
            return local_ips
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr")
                    if ip:
                        local_ips.add(ip)
        return local_ips

    def _get_network_hosts(self) -> Set[str]:
        """Enumerate potential hosts from interface netmasks."""
        if netifaces is None:
            return set()
        local_ips = self._get_local_addresses()
        hosts: Set[str] = set()
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                continue
            for addr in addrs[netifaces.AF_INET]:
                ip = addr.get("addr")
                netmask = addr.get("netmask")
                if not ip or not netmask or ip.startswith("127."):
                    continue
                try:
                    network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                except Exception:
                    continue
                for host in network.hosts():
                    host_str = str(host)
                    if host_str not in local_ips:
                        hosts.add(host_str)
        return hosts

    def _is_vision_model(self, model_name: str) -> bool:
        """Check whether the provided model id looks vision-capable."""
        for pattern in self.qwen_patterns:
            if pattern.search(model_name):
                return True
        model_lower = model_name.lower()
        for pattern in self.additional_vision_models:
            if pattern.lower() in model_lower:
                return True
        return False

    async def _check_port(self, host: str, port: int) -> bool:
        """Return True if the host:port accepts TCP connections."""
        if not port:
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

    async def _fetch_models(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
    ) -> List[str]:
        """Retrieve matching models from an OpenAI-compatible server."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout, connect=0.5)
            async with session.get(f"{base_url}/v1/models", timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                payload = await resp.json()
        except Exception:
            return []

        vision_models: List[str] = []
        for model in payload.get("data", []):
            model_id = model.get("id", "")
            if model_id and self._is_vision_model(model_id):
                vision_models.append(model_id)
        return vision_models

    async def _discover_localhost(
        self,
        session: aiohttp.ClientSession,
    ) -> Dict[str, Optional[Dict]]:
        """Check localhost ports first since they are most common."""
        local_ips = self._get_local_addresses()
        results: Dict[str, Optional[Dict]] = {"lm_studio": None, "ollama": None}

        if await self._check_port("127.0.0.1", self.lm_studio_port):
            models = await self._fetch_models(session, f"http://127.0.0.1:{self.lm_studio_port}")
            if models:
                results["lm_studio"] = {
                    "server_address": f"http://127.0.0.1:{self.lm_studio_port}",
                    "local_addresses": sorted(f"http://{ip}:{self.lm_studio_port}" for ip in local_ips),
                    "vision_models": models,
                }

        if await self._check_port("127.0.0.1", self.ollama_port):
            models = await self._fetch_models(session, f"http://127.0.0.1:{self.ollama_port}")
            if models:
                results["ollama"] = {
                    "server_address": f"http://127.0.0.1:{self.ollama_port}",
                    "local_addresses": sorted(f"http://{ip}:{self.ollama_port}" for ip in local_ips),
                    "vision_models": models,
                }

        return results

    async def _check_port_and_service(
        self,
        host: str,
        service_type: str,
        port: int,
    ) -> Tuple[str, str, bool]:
        """Return tuple describing whether a host:port is reachable."""
        return (service_type, host, await self._check_port(host, port))

    async def _fetch_server_info(
        self,
        session: aiohttp.ClientSession,
        service_type: str,
        url: str,
    ) -> Tuple[str, Optional[Dict]]:
        """Return the server metadata and available models."""
        models = await self._fetch_models(session, url)
        if models:
            return (
                service_type,
                {
                    "server_address": url,
                    "vision_models": models,
                },
            )
        return (service_type, None)

    async def _discover_network(
        self,
        session: aiohttp.ClientSession,
    ) -> Dict[str, List[Dict]]:
        """Scan non-localhost network peers for active services."""
        hosts = self._get_network_hosts()
        results: Dict[str, List[Dict]] = {"lm_studio": [], "ollama": []}
        if not hosts:
            return results

        scan_tasks = []
        for host in hosts:
            scan_tasks.append(self._check_port_and_service(host, "lm_studio", self.lm_studio_port))
            scan_tasks.append(self._check_port_and_service(host, "ollama", self.ollama_port))

        active = {"lm_studio": set(), "ollama": set()}
        scan_results = await asyncio.gather(*scan_tasks, return_exceptions=True)
        for item in scan_results:
            if isinstance(item, tuple) and item[2]:
                service_type, host = item[0], item[1]
                active[service_type].add(host)

        fetch_tasks = []
        for host in active["lm_studio"]:
            fetch_tasks.append(
                self._fetch_server_info(session, "lm_studio", f"http://{host}:{self.lm_studio_port}")
            )
        for host in active["ollama"]:
            fetch_tasks.append(
                self._fetch_server_info(session, "ollama", f"http://{host}:{self.ollama_port}")
            )

        if not fetch_tasks:
            return results

        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        for item in fetch_results:
            if isinstance(item, tuple) and item[1]:
                service_type, server_info = item
                results[service_type].append(server_info)
        return results

    async def discover(self) -> Dict[str, List[Dict]]:
        """Run full discovery returning LM Studio and Ollama matches."""
        connector = aiohttp.TCPConnector(limit=30, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            localhost = await self._discover_localhost(session)
            network = await self._discover_network(session)

        results: Dict[str, List[Dict]] = {"lm_studio": [], "ollama": []}
        if localhost["lm_studio"]:
            results["lm_studio"].append(localhost["lm_studio"])
        if localhost["ollama"]:
            results["ollama"].append(localhost["ollama"])
        results["lm_studio"].extend(network["lm_studio"])
        results["ollama"].extend(network["ollama"])
        return results

    async def discover_lm_studio(self) -> List[Dict]:
        """Return only LM Studio discoveries."""
        original = self.ollama_port
        self.ollama_port = 0
        try:
            results = await self.discover()
            return results["lm_studio"]
        finally:
            self.ollama_port = original

    async def discover_ollama(self) -> List[Dict]:
        """Return only Ollama discoveries."""
        original = self.lm_studio_port
        self.lm_studio_port = 0
        try:
            results = await self.discover()
            return results["ollama"]
        finally:
            self.lm_studio_port = original


__all__ = ["VisionModelDiscovery"]
