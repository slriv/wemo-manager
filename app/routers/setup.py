"""Mobile setup settings and APK routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import SetupConfigRead, SetupConfigUpdate
from ..services import settings
from ..services.discovery import local_ipv4_for

router = APIRouter(prefix="/api/setup", tags=["setup"])

# Configurable so a rebuilt APK can be dropped into a mounted volume.
_DEFAULT_APK_PATH = Path(__file__).resolve().parent.parent / "static" / "wemo-manager.apk"
APK_PATH = Path(os.environ.get("WEMO_MANAGER_APK_PATH", str(_DEFAULT_APK_PATH)))
APK_MEDIA_TYPE = "application/vnd.android.package-archive"


@router.get("/config", response_model=SetupConfigRead)
def get_config(request: Request, db: Session = Depends(get_db)) -> SetupConfigRead:
    return SetupConfigRead(
        wifi_ssid=settings.get_setting(db, settings.WIFI_SSID) or "",
        wifi_password=settings.get_setting(db, settings.WIFI_PASSWORD) or "",
        apk_available=APK_PATH.is_file(),
        server_host=local_ipv4_for(request.client.host if request.client else ""),
    )


@router.put("/config", response_model=SetupConfigRead)
def update_config(
    request: Request, payload: SetupConfigUpdate, db: Session = Depends(get_db)
) -> SetupConfigRead:
    """Store the Wi-Fi credentials handed to devices during registration."""
    if payload.wifi_ssid is not None:
        settings.set_setting(db, settings.WIFI_SSID, payload.wifi_ssid)
    if payload.wifi_password is not None:
        settings.set_setting(db, settings.WIFI_PASSWORD, payload.wifi_password)
    return get_config(request, db)


@router.get("/apk")
def download_apk() -> FileResponse:
    """Serve the Android app for sideloading."""
    if not APK_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="No APK has been built yet — run `make apk` on a machine with "
            "the Android SDK and restart.",
        )
    return FileResponse(
        APK_PATH, media_type=APK_MEDIA_TYPE, filename="wemo-manager.apk"
    )
