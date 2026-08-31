"""Ephemeral cache of the latest detect scan, keyed by UDN and replaced by the next scan."""

from __future__ import annotations

import threading

import pywemo

_lock = threading.Lock()
_pending: dict[str, pywemo.WeMoDevice] = {}


def store(devices: list[pywemo.WeMoDevice]) -> None:
    with _lock:
        _pending.clear()
        for device in devices:
            _pending[device.udn] = device


def get(udn: str) -> pywemo.WeMoDevice | None:
    with _lock:
        return _pending.get(udn)


def pop_many(udns: list[str]) -> list[pywemo.WeMoDevice]:
    with _lock:
        found = []
        for udn in udns:
            device = _pending.pop(udn, None)
            if device is not None:
                found.append(device)
        return found
