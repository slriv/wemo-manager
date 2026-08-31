"""Server-rendered HTML pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import repository
from .templating import templates

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    devices = repository.list_devices(db)
    return templates.TemplateResponse(
        request, "index.html", {"devices": devices}
    )


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "setup.html", {})


@router.get("/devices/{device_id}", response_class=HTMLResponse)
def device_detail(
    request: Request, device_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    device = repository.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return templates.TemplateResponse(
        request, "device_detail.html", {"device": device}
    )
