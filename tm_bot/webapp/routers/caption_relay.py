"""Caption Relay has its own identity realm, never a user/admin session."""
import time
import io
import zipfile
from pathlib import Path
from collections import OrderedDict
from threading import Lock
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, ConfigDict

from repositories.caption_relay_repo import CaptionRelayRepository
from repositories.video_transcript_fetch_queue_repo import VideoTranscriptFetchQueueRepository, LeaseLost
from services.caption_models import Completion
from webapp.dependencies import get_admin_user


class BoundedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            rate_limit(request.client.host if request.client else "unknown")
            # Bound actual streamed bytes, including chunked/missing-length uploads.
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 2_000_000:
                    raise HTTPException(413, "Caption request too large")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            try:
                response = await original(request)
            except RequestValidationError:
                # Never reflect tokens or caption bodies in error messages.
                raise HTTPException(422, "Invalid caption relay request")
            response.headers["Cache-Control"] = "no-store"
            return response
        return handler


router = APIRouter(prefix="/api/caption-relay", tags=["caption-relay"], route_class=BoundedRoute)
_attempts = OrderedDict()
_lock = Lock()


@router.get("/download")
def download():
    # Curated public source bundle, never environment/config/credential files.
    folder = Path(__file__).resolve().parents[3] / "scripts" / "caption_relay"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("__init__.py", "__main__.py", "client.py", "fetch.py",
                     "pyproject.toml", "xaana-caption-relay.service"):
            archive.write(folder / name, "xaana-caption-relay/" + name)
    return Response(output.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="xaana-caption-relay.zip"'})


def rate_limit(key):
    # Bounded best-effort request throttle; DB claim cooldown also applies
    # across replicas. Identity secrecy does not depend on IP guessing limits.
    now = time.monotonic()
    with _lock:
        start, count = _attempts.pop(key, (now, 0))
        if now-start >= 60:
            start, count = now, 0
        _attempts[key] = (start, count+1)
        if len(_attempts) > 4096:
            _attempts.popitem(last=False)
        if count >= 30:
            raise HTTPException(429, "Try again later", headers={"Retry-After": "60"})


def device(request: Request, authorization: Optional[str] = Header(None)):
    token = (authorization or "").removeprefix("Bearer ")
    identity = CaptionRelayRepository().authenticate(token)
    if not identity:
        raise HTTPException(401, "Invalid or revoked relay token")
    return identity


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")


class DeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f]+$")


@router.post("/pair")
def pair(body: PairRequest, request: Request):
    result = CaptionRelayRepository().pair(body.code)
    if not result:
        raise HTTPException(401, "Pairing code invalid, expired or already used")
    return result


@router.post("/claim")
def claim(worker_id: str = Depends(device)):
    try:
        return {"job": VideoTranscriptFetchQueueRepository().claim(worker_id), "poll_after": 20}
    except LeaseLost:
        raise HTTPException(401, "Device revoked")


@router.post("/complete", status_code=204)
def complete(body: Completion, worker_id: str = Depends(device)):
    try:
        VideoTranscriptFetchQueueRepository().finish(
            body.video_id, body.lease_token, worker_id,
            body.transcript.model_dump() if body.transcript else None, body.error,
        )
    except LeaseLost:
        raise HTTPException(409, "Lease expired or no longer owned")
    return Response(status_code=204)


@router.get("/devices")
def devices(admin: int = Depends(get_admin_user)):
    return CaptionRelayRepository().list_devices()


@router.post("/devices")
def create_device(body: DeviceRequest, admin: int = Depends(get_admin_user)):
    return CaptionRelayRepository().create(body.name.strip(), admin)


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(device_id: UUID, admin: int = Depends(get_admin_user)):
    CaptionRelayRepository().revoke(str(device_id))
    return Response(status_code=204)
