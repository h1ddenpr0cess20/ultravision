"""Auto-discovery for LM Studio/Ollama vision model servers."""

from __future__ import annotations

import asyncio
import ipaddress
import re
from typing import Dict, List, Optional, Set, Tuple

import aiohttp
import netifaces

DEFAULT_VISION_MODEL_HINTS = ("gemma3",)


class VisionModelDiscovery:
    """Discovery service for vision models on LM Studio and Ollama servers."""

    def __init__(
        self,
        lm_studio_port: int = 1234,
        ollama_port: int = 11434,
        timeout: float = 2.0,
        additional_vision_models: Optional[List[str]] = None,
    ) -> None:
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
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr")
                    if ip:
                        local_ips.add(ip)
        return local_ips

    def _get_network_hosts(self) -> Set[str]:
        """Enumerate all potential LAN hosts excluding the known interface IPs."""

        local_ips = self._get_local_addresses()
        potential_hosts: Set[str] = set()
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
                    for host in network.hosts():
                        host_str = str(host)
                        if host_str not in local_ips:
                            potential_hosts.add(host_str)
                except Exception:
                    continue
        return potential_hosts

    def _is_vision_model(self, model_name: str) -> bool:
        """Return ``True`` when the model id looks like a multimodal/vision model."""

        for pattern in self.qwen_patterns:
            if pattern.search(model_name):
                return True

        model_lower = model_name.lower()
        for needle in self.additional_vision_models:
            if needle.lower() in model_lower:
                return True
        return False

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

    async def _fetch_models(self, session: aiohttp.ClientSession, base_url: str) -> List[str]:
        """Return the filtered models from a `/v1/models` endpoint."""

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout, connect=0.5)
            async with session.get(f"{base_url}/v1/models", timeout=timeout) as response:
                if response.status != 200:
                    return []
                data = await response.json()
        except Exception:
            return []

        vision_models: List[str] = []
        for row in data.get("data", []):
            model_id = row.get("id", "")
            if model_id and self._is_vision_model(model_id):
                vision_models.append(model_id)
        return vision_models

    async def _discover_localhost(self, session: aiohttp.ClientSession) -> Dict[str, Optional[Dict]]:
        """Return ``lm_studio`` / ``ollama`` entries found on localhost."""

        local_ips = self._get_local_addresses()
        results: Dict[str, Optional[Dict]] = {"lm_studio": None, "ollama": None}

        if await self._check_port("127.0.0.1", self.lm_studio_port):
            models = await self._fetch_models(session, f"http://127.0.0.1:{self.lm_studio_port}")
            if models:
                results["lm_studio"] = {
                    "server_address": f"http://127.0.0.1:{self.lm_studio_port}",
                    "local_addresses": sorted(
                        f"http://{ip}:{self.lm_studio_port}" for ip in local_ips
                    ),
                    "vision_models": models,
                }

        if await self._check_port("127.0.0.1", self.ollama_port):
            models = await self._fetch_models(session, f"http://127.0.0.1:{self.ollama_port}")
            if models:
                results["ollama"] = {
                    "server_address": f"http://127.0.0.1:{self.ollama_port}",
                    "local_addresses": sorted(
                        f"http://{ip}:{self.ollama_port}" for ip in local_ips
                    ),
                    "vision_models": models,
                }

        return results

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

    async def discover_lm_studio(self) -> List[Dict]:
        """Return only LM Studio hosts."""

        old_port = self.ollama_port
        self.ollama_port = 0
        try:
            results = await self.discover()
        finally:
            self.ollama_port = old_port
        return results["lm_studio"]

    async def discover_ollama(self) -> List[Dict]:
        """Return only Ollama hosts."""

        old_port = self.lm_studio_port
        self.lm_studio_port = 0
        try:
            results = await self.discover()
        finally:
            self.lm_studio_port = old_port
        return results["ollama"]


__all__ = ["VisionModelDiscovery", "DEFAULT_VISION_MODEL_HINTS"]
