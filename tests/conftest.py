"""Test configuration with an optional pywemo stub."""

from __future__ import annotations

import sys
import types

import pytest


def _install_pywemo_stub() -> None:
    if "pywemo" in sys.modules:
        return
    try:
        import pywemo  # noqa: F401

        return
    except ImportError:
        pass

    pywemo_pkg = types.ModuleType("pywemo")
    discovery_mod = types.ModuleType("pywemo.discovery")
    ouimeaux_mod = types.ModuleType("pywemo.ouimeaux_device")
    exceptions_mod = types.ModuleType("pywemo.exceptions")

    def device_from_description(url, *, debug=False):  # pragma: no cover
        raise NotImplementedError("stub")

    def probe_wemo(host, ports=(), probe_timeout=0.0, match_udn=None):  # pragma: no cover
        return None

    class PyWeMoException(Exception):
        pass

    discovery_mod.device_from_description = device_from_description
    ouimeaux_mod.PROBE_PORTS = (49153, 49152)
    ouimeaux_mod.probe_wemo = probe_wemo
    exceptions_mod.PyWeMoException = PyWeMoException

    class WeMoDevice:  # pragma: no cover
        pass

    class SubscriptionRegistry:  # pragma: no cover
        def start(self):
            pass

        def stop(self):
            pass

        def register(self, device):
            pass

        def unregister(self, device):
            pass

        def on(self, device, type_filter, callback):
            pass

    pywemo_pkg.discovery = discovery_mod
    pywemo_pkg.ouimeaux_device = ouimeaux_mod
    pywemo_pkg.exceptions = exceptions_mod
    pywemo_pkg.WeMoDevice = WeMoDevice
    pywemo_pkg.SubscriptionRegistry = SubscriptionRegistry

    sys.modules["pywemo"] = pywemo_pkg
    sys.modules["pywemo.discovery"] = discovery_mod
    sys.modules["pywemo.ouimeaux_device"] = ouimeaux_mod
    sys.modules["pywemo.exceptions"] = exceptions_mod


_install_pywemo_stub()


@pytest.fixture
def pywemo_is_real() -> bool:
    """True if the real pywemo package, not the stub, is importable."""
    import pywemo

    return not hasattr(pywemo, "__wemo_manager_stub__")
