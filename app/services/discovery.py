"""Device discovery by concurrent TCP probing."""

from __future__ import annotations

import dataclasses
import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import ifaddr
from pywemo.discovery import device_from_description
from pywemo.ouimeaux_device import PROBE_PORTS, probe_wemo

LOG = logging.getLogger(__name__)

DEFAULT_PROBE_TIMEOUT = 2.0  # seconds
DEFAULT_MAX_WORKERS = 32


@dataclasses.dataclass
class ScanResult:
    host: str
    found: bool
    setup_url: str | None = None
    error: str | None = None


def default_network() -> str:
    """Return an active IPv4 network or a private /24 fallback."""
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4 and ip.ip not in ("127.0.0.1",):
                network = ipaddress.ip_network(
                    f"{ip.ip}/{ip.network_prefix}", strict=False
                )
                if network.num_addresses > 1:
                    return str(network)
    return "192.168.1.0/24"


def local_ipv4_for(peer: str) -> str:
    """Return this host's IPv4 address on the same subnet as ``peer``, or "" if none."""
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return ""
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if not ip.is_IPv4 or ip.ip == "127.0.0.1":
                continue
            network = ipaddress.ip_network(
                f"{ip.ip}/{ip.network_prefix}", strict=False
            )
            if peer_ip in network:
                return ip.ip
    return ""


def _hosts_for_target(target: str) -> list[str]:
    """Expand a CIDR or IP address into probe targets."""
    network = ipaddress.ip_network(target, strict=False)
    if network.num_addresses == 1:
        return [str(network.network_address)]
    return [str(host) for host in network.hosts()]


def _probe_host(host: str, timeout: float) -> ScanResult:
    try:
        port = probe_wemo(host, ports=PROBE_PORTS, probe_timeout=timeout)
    except Exception as err:  # pragma: no cover
        LOG.debug("Unexpected error probing %s: %r", host, err)
        return ScanResult(host=host, found=False, error=str(err))

    if port is None:
        return ScanResult(host=host, found=False)

    return ScanResult(
        host=host, found=True, setup_url=f"http://{host}:{port}/setup.xml"
    )


def scan_network(
    target: str,
    *,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    max_workers: int = DEFAULT_MAX_WORKERS,
):
    """Probe a CIDR or IP address for WeMo devices."""
    hosts = _hosts_for_target(target)
    devices = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_host, host, timeout): host for host in hosts
        }
        for future in as_completed(futures):
            result = future.result()
            if not result.found or not result.setup_url:
                continue
            device = device_from_description(result.setup_url)
            if device is not None:
                devices.append(device)

    return devices
