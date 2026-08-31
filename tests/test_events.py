"""Unit tests for app.services.events."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.services.events import DeviceEventBroadcaster


@pytest.mark.asyncio
async def test_emit_delivers_to_subscriber():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.bind_loop(asyncio.get_running_loop())
    queue = broadcaster.subscribe()

    broadcaster.emit()

    await asyncio.wait_for(queue.get(), timeout=1)


@pytest.mark.asyncio
async def test_emit_without_subscribers_is_a_noop():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.bind_loop(asyncio.get_running_loop())

    broadcaster.emit()  # must not raise


def test_emit_before_bind_loop_is_a_noop():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.emit()  # no loop bound yet; must not raise


@pytest.mark.asyncio
async def test_emit_coalesces_pending_signals():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.bind_loop(asyncio.get_running_loop())
    queue = broadcaster.subscribe()

    broadcaster.emit()
    broadcaster.emit()
    await asyncio.sleep(0)

    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.bind_loop(asyncio.get_running_loop())
    queue = broadcaster.subscribe()
    broadcaster.unsubscribe(queue)

    broadcaster.emit()
    await asyncio.sleep(0)

    assert queue.empty()


@pytest.mark.asyncio
async def test_emit_from_background_thread_is_delivered():
    broadcaster = DeviceEventBroadcaster()
    broadcaster.bind_loop(asyncio.get_running_loop())
    queue = broadcaster.subscribe()

    thread = threading.Thread(target=broadcaster.emit)
    thread.start()
    thread.join()

    await asyncio.wait_for(queue.get(), timeout=1)
