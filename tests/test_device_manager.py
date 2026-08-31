"""Unit tests for DeviceManager state and reset dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pywemo.exceptions import PyWeMoException

from app.services.device_manager import DeviceManager


class _FakeSwitch:
    def __init__(self):
        self.state = 0

    def set_state(self, state):
        self.state = state

    def get_state(self, force_update=False):
        return self.state


class _FakeDimmer(_FakeSwitch):
    def __init__(self):
        super().__init__()
        self.brightness = 0

    def set_brightness(self, level):
        self.brightness = level
        self.state = 1

    def get_brightness(self, force_update=False):
        return self.brightness


class _FakeResettable(_FakeSwitch):
    def __init__(self):
        super().__init__()
        self.last_reset = None

    def reset(self, data, wifi):
        self.last_reset = (data, wifi)
        return "success"


UDN = "uuid:Test-1_0-1"


def _manager_with(device):
    manager = DeviceManager()
    manager._live_devices[UDN] = device  # noqa: SLF001
    return manager


def test_on_off_dispatches_to_set_state():
    device = _FakeSwitch()
    manager = _manager_with(device)
    state, brightness = manager.set_device_state(UDN, on=True)
    assert state == 1
    assert brightness is None


def test_level_dispatches_to_set_brightness():
    device = _FakeDimmer()
    manager = _manager_with(device)
    state, brightness = manager.set_device_state(UDN, level=42)
    assert state == 1
    assert brightness == 42


def test_level_on_non_dimmer_raises():
    device = _FakeSwitch()
    manager = _manager_with(device)
    with pytest.raises(PyWeMoException):
        manager.set_device_state(UDN, level=50)


def test_unknown_udn_raises():
    manager = DeviceManager()
    with pytest.raises(PyWeMoException):
        manager.set_device_state("uuid:missing", on=True)


def test_reset_dispatches_to_device_reset():
    device = _FakeResettable()
    manager = _manager_with(device)
    status = manager.reset_device(UDN, data=True, wifi=False)
    assert status == "success"
    assert device.last_reset == (True, False)


def test_reset_unknown_udn_raises():
    manager = DeviceManager()
    with pytest.raises(PyWeMoException):
        manager.reset_device("uuid:missing", data=True, wifi=True)


def test_start_defers_known_device_reconnection_to_poll_loop():
    manager = DeviceManager()
    with patch.object(manager.registry, "start") as registry_start, patch.object(
        manager, "_load_known_devices"
    ) as load_known_devices:
        manager.start()

    registry_start.assert_called_once()
    load_known_devices.assert_not_called()
    assert manager._started is True  # noqa: SLF001
