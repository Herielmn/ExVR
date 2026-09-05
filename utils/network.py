from __future__ import annotations

import psutil
import socket

VIRTUAL_ADAPTER_KEYWORDS = [
    "virtual", "vmware", "virtualbox", "vpn", "docker", "vethernet",
    "clash", "xray", "v2ray", "sing-box", "tun", "loopback",
]
WIFI_KEYWORDS = ["wlan", "wi-fi", "wireless", "无线"]
ETHERNET_KEYWORDS = ["ethernet", "eth", "以太网"]


def is_private(ip: str) -> bool:
    try:
        octets = [int(part) for part in ip.split(".")]
        if len(octets) != 4:
            return False
        if octets[0] == 10:
            return True
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        if octets[0] == 192 and octets[1] == 168:
            return True
    except (ValueError, IndexError):
        return False
    return False


def private_ips() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    for name, addresses in interfaces.items():
        state = stats.get(name)
        if not state or not state.isup:
            continue
        lowered = name.lower()
        if any(keyword in lowered for keyword in VIRTUAL_ADAPTER_KEYWORDS):
            continue
        for address in addresses:
            if address.family == socket.AF_INET and is_private(address.address):
                found.append((name, address.address))
    return found


def interface_label(name: str) -> str:
    lowered = name.lower()
    if any(keyword in lowered for keyword in WIFI_KEYWORDS):
        return "Wi-Fi/WLAN"
    if any(keyword in lowered for keyword in ETHERNET_KEYWORDS):
        return "Ethernet"
    return name
