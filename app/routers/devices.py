"""REST API routes for devices: list, read, update, delete, detect, and state control."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from concurrent.futures import ThreadPoolExecutor, wait

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pywemo.ouimeaux_device.api.rules_db import rules_db_from_device
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DeviceStatus
from ..schemas import (
    AllOffRequest,
    CommitDetectRequest,
    DetectedDevice,
    DetectRequest,
    DetectResponse,
    DeviceRead,
    DeviceUpdate,
    ResetRequest,
    SetStateRequest,
)
from ..services import detect_cache, repository
from ..services.device_manager import device_manager
from ..services.discovery import default_network, scan_network
from ..services.events import device_events
from ..services.rule_summary import calendar_events, consolidate_rules, summarize_rules

LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])

HEARTBEAT_INTERVAL_SECONDS = 15.0
RULES_SUMMARY_SOURCE_LIMIT = 4
RULES_SUMMARY_TIMEOUT_SECONDS = 12.0


def _to_detected(device) -> DetectedDevice:
    return DetectedDevice(
        udn=device.udn,
        host=device.host,
        port=device.port,
        setup_url=device.session.url,
        name=device.name,
        mac=device.mac,
        manufacturer=device.manufacturer,
        model=device.model,
        model_name=device.model_name,
        serial_number=device.serial_number,
        firmware_version=device.firmware_version,
        device_type=type(device).__name__,
    )


@router.get("", response_model=list[DeviceRead])
def list_devices(db: Session = Depends(get_db)) -> list[DeviceRead]:
    """Return all known devices."""
    return [DeviceRead.model_validate(d) for d in repository.list_devices(db)]


@router.get("/default-network")
def get_default_network() -> dict[str, str]:
    """Return this host's best-guess active IPv4 CIDR and its dotted-decimal netmask."""
    cidr = default_network()
    return {"network": cidr, "netmask": str(ipaddress.ip_network(cidr).netmask)}


@router.get("/events")
async def device_events_stream(request: Request) -> StreamingResponse:
    """SSE stream signalling that the device table changed; clients re-fetch GET /api/devices."""
    queue = device_events.subscribe()

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                    )
                    yield "data: changed\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            device_events.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/rules/summary")
def get_all_rules_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    """Read and deduplicate rules from connected devices."""
    devices = repository.list_devices(db)
    device_names = {device.udn: device.name for device in devices}
    connected = sorted(
        (device for device in devices if device_manager.get_live_device(device.udn)),
        key=lambda device: device.name.casefold(),
    )[:RULES_SUMMARY_SOURCE_LIMIT]

    def load_device_rules(device) -> tuple[int, list[dict]]:
        return device.id, summarize_rules(_read_rules_database(device.udn), device_names)

    refreshed_device_ids: set[int] = set()
    unavailable: list[str] = []
    executor = ThreadPoolExecutor(max_workers=len(connected) or 1)
    futures = {executor.submit(load_device_rules, device): device.name for device in connected}
    done, pending = wait(futures, timeout=RULES_SUMMARY_TIMEOUT_SECONDS)
    for future in done:
        try:
            device_id, summary = future.result()
            repository.cache_rules_summary(db, device_id, summary)
            refreshed_device_ids.add(device_id)
        except Exception:
            LOG.info("Could not read rules from %s", futures[future], exc_info=True)
            unavailable.append(futures[future])
    for future in pending:
        future.cancel()
        unavailable.append(futures[future])
    executor.shutdown(wait=False, cancel_futures=True)

    cached_summaries = []
    cached_sources = []
    for device in devices:
        cached = repository.get_cached_rules_summary(db, device.id)
        if cached is None:
            continue
        cached_summaries.append((device.name, json.loads(cached.summary_json)))
        if device.id not in refreshed_device_ids:
            cached_sources.append(device.name)

    return {
        "rules": consolidate_rules(cached_summaries),
        "sources_checked": len(connected),
        "sources_unavailable": sorted(unavailable),
        "cached_sources": sorted(cached_sources),
    }


@router.get("/rules/summary/cached")
def get_cached_all_rules_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    """Return cached consolidated rules without making any device network requests."""
    cached_summaries = []
    cached_sources = []
    for device in repository.list_devices(db):
        cached = repository.get_cached_rules_summary(db, device.id)
        if cached is None:
            continue
        cached_summaries.append((device.name, json.loads(cached.summary_json)))
        cached_sources.append(device.name)
    return {
        "rules": consolidate_rules(cached_summaries),
        "sources_checked": 0,
        "sources_unavailable": [],
        "cached_sources": sorted(cached_sources),
    }


@router.get("/rules/calendar")
def get_cached_rules_calendar(db: Session = Depends(get_db)) -> dict[str, object]:
    """Return cached schedule events without contacting devices."""
    cached_summaries = []
    sources = []
    for device in repository.list_devices(db):
        cached = repository.get_cached_rules_summary(db, device.id)
        if cached is None:
            continue
        fetched_at = cached.fetched_at.isoformat()
        sources.append({"name": device.name, "fetched_at": fetched_at})
        cached_summaries.append((device.name, json.loads(cached.summary_json)))
    latest_fetched_at = max((source["fetched_at"] for source in sources), default="")
    events = calendar_events(
        consolidate_rules(cached_summaries), "cached device snapshots", latest_fetched_at
    )
    return {"events": events, "sources": sources}


@router.post("/all-off")
def turn_all_off(
    payload: AllOffRequest = AllOffRequest(), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Turn off known devices (or just ``device_ids``). Unreachable devices are skipped."""
    rows = repository.list_devices(db)
    if payload.device_ids is not None:
        wanted = set(payload.device_ids)
        rows = [row for row in rows if row.id in wanted]

    succeeded = 0
    failed = 0
    for row in rows:
        try:
            state, brightness = device_manager.set_device_state(row.udn, on=False)
        except Exception:
            failed += 1
            continue
        repository.mark_state(
            db, row, binary_state=state, brightness=brightness, status=DeviceStatus.ONLINE
        )
        succeeded += 1
    return {"succeeded": succeeded, "failed": failed}


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(device_id: int, db: Session = Depends(get_db)) -> DeviceRead:
    """Return full technical detail for one device."""
    device = repository.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceRead.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)
) -> DeviceRead:
    """Update editable metadata on a device."""
    device = repository.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if payload.name is not None:
        device.name = payload.name
    db.add(device)
    db.commit()
    db.refresh(device)
    device_events.emit()
    return DeviceRead.model_validate(device)


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)) -> None:
    """Remove a device from the known-devices list."""
    device = repository.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device_manager.forget_device(device.udn)
    repository.delete_device(db, device_id)


@router.post("/{device_id}/state", response_model=DeviceRead)
def set_device_state(
    device_id: int, payload: SetStateRequest, db: Session = Depends(get_db)
) -> DeviceRead:
    """Turn a device on/off, or set a dimmer's brightness level."""
    device_row = repository.get_device(db, device_id)
    if device_row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        state, brightness = device_manager.set_device_state(
            device_row.udn, on=payload.on, level=payload.level
        )
    except Exception as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    device_row = repository.mark_state(
        db, device_row, binary_state=state, brightness=brightness, status=DeviceStatus.ONLINE
    )
    return DeviceRead.model_validate(device_row)


@router.post("/{device_id}/reset")
def reset_device(device_id: int, payload: ResetRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """Reset name, icon, and rules, and optionally WiFi credentials."""
    device_row = repository.get_device(db, device_id)
    if device_row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        status = device_manager.reset_device(device_row.udn, data=payload.data, wifi=payload.wifi)
    except Exception as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    return {"status": status}


@router.get("/{device_id}/rules")
def get_device_rules(device_id: int, db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    """Return the raw, read-only rules database."""
    device_row = repository.get_device(db, device_id)
    if device_row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        return _read_rules_database(device_row.udn)
    except Exception as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.get("/{device_id}/rules/summary")
def get_device_rules_summary(device_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return a human-readable, read-only summary of this device's rules database."""
    device_row = repository.get_device(db, device_id)
    if device_row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        rules_db = _read_rules_database(device_row.udn)
    except Exception as err:
        cached = repository.get_cached_rules_summary(db, device_id)
        if cached is None:
            raise HTTPException(status_code=502, detail=str(err)) from err
        return {
            "rules": json.loads(cached.summary_json),
            "cached": True,
            "fetched_at": cached.fetched_at.isoformat(),
        }
    device_names = {device.udn: device.name for device in repository.list_devices(db)}
    summary = summarize_rules(rules_db, device_names)
    cached = repository.cache_rules_summary(db, device_id, summary)
    return {"rules": summary, "cached": False, "fetched_at": cached.fetched_at.isoformat()}


def _read_rules_database(udn: str) -> dict[str, list[dict]]:
    """Fetch every table from a connected device's on-device rules database."""
    live_device = device_manager.get_live_device(udn)
    if live_device is None:
        raise HTTPException(status_code=502, detail="Device is not connected")
    with rules_db_from_device(live_device) as rules:
        cursor = rules.db.cursor()
        tables = [
            row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            table: [
                {k: (v.hex() if isinstance(v, bytes) else v) for k, v in dict(row).items()}
                for row in cursor.execute(f"SELECT * FROM {table}")  # noqa: S608
            ]
            for table in tables
        }


@router.post("/detect", response_model=DetectResponse)
async def detect(payload: DetectRequest, db: Session = Depends(get_db)) -> DetectResponse:
    """Scan a CIDR/IP for WeMo devices. ``persist=true`` upserts everything found."""
    devices = await asyncio.to_thread(
        scan_network, payload.target, timeout=payload.timeout
    )
    detect_cache.store(devices)

    if payload.persist:
        for device in devices:
            repository.upsert_from_pywemo(db, device)
            device_manager.register_new_device(device)

    return DetectResponse(
        target=payload.target,
        devices=[_to_detected(d) for d in devices],
        persisted=payload.persist,
    )


@router.post("/detect/commit", response_model=list[DeviceRead])
def commit_detect(
    payload: CommitDetectRequest, db: Session = Depends(get_db)
) -> list[DeviceRead]:
    """Persist a chosen subset of devices from the most recent detect scan."""
    devices = detect_cache.pop_many(payload.udns)
    if not devices:
        raise HTTPException(
            status_code=404,
            detail="No matching devices found in the last scan (results expire after "
            "a new scan runs).",
        )
    saved = []
    for device in devices:
        row = repository.upsert_from_pywemo(db, device)
        device_manager.register_new_device(device)
        saved.append(row)
    return [DeviceRead.model_validate(d) for d in saved]
