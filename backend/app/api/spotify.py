"""Spotify player API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import ConnectedAccount, User
from app.schemas.spotify import (
    SpotifyActionStatus,
    SpotifyArtist,
    SpotifyDevice,
    SpotifyPlayerState,
    SpotifyTrack,
    SpotifyTransferRequest,
    SpotifyTransferSummary,
)
from app.services.spotify_service import SpotifyAPIError, SpotifyService
from app.services.spotify_transfer_service import SpotifyTransferService


READ_SCOPES = {"user-read-playback-state", "user-read-currently-playing"}
MODIFY_SCOPES = {"user-modify-playback-state"}
PLAYLIST_READ_SCOPES = {"playlist-read-private", "playlist-read-collaborative"}
PLAYLIST_MODIFY_SCOPES = {"playlist-modify-private", "playlist-modify-public"}
LIBRARY_READ_SCOPES = {"user-library-read"}
LIBRARY_MODIFY_SCOPES = {"user-library-modify"}

router = APIRouter(prefix="/spotify", tags=["spotify"])


def _scope_set(account: ConnectedAccount) -> set[str]:
    raw = (account.scopes or "").replace(",", " ")
    return {s.strip() for s in raw.split() if s.strip()}


def _require_scopes(account: ConnectedAccount, required: set[str]) -> None:
    missing = required - _scope_set(account)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Spotify permissions missing: {missing_list}. Reconnect Spotify.",
        )


def _get_spotify_account(
    db: Session,
    current_user: User,
    account_id: UUID | None,
) -> ConnectedAccount:
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "spotify",
    )
    if account_id:
        stmt = stmt.where(ConnectedAccount.id == account_id)
    stmt = stmt.order_by(ConnectedAccount.created_at.desc())
    account = db.execute(stmt).scalars().first()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spotify account not found. Connect Spotify first.",
        )
    return account


def _map_player_state(account_id: UUID, state: dict | None) -> SpotifyPlayerState:
    if not state:
        return SpotifyPlayerState(account_id=account_id, has_active_device=False)

    item = state.get("item") or {}
    artists = [SpotifyArtist(name=a.get("name", "Unknown")) for a in item.get("artists", [])]
    images = (item.get("album") or {}).get("images") or []
    album_image_url = images[0]["url"] if images else None
    track = None
    if item:
        track = SpotifyTrack(
            id=item.get("id"),
            name=item.get("name", "Unknown Track"),
            artists=artists,
            album_name=(item.get("album") or {}).get("name"),
            album_image_url=album_image_url,
            duration_ms=item.get("duration_ms"),
            external_url=(item.get("external_urls") or {}).get("spotify"),
        )

    device_data = state.get("device") or {}
    device = None
    if device_data:
        device = SpotifyDevice(
            id=device_data.get("id"),
            name=device_data.get("name", "Unknown Device"),
            type=device_data.get("type"),
            volume_percent=device_data.get("volume_percent"),
            is_active=bool(device_data.get("is_active")),
            is_restricted=bool(device_data.get("is_restricted")),
        )

    return SpotifyPlayerState(
        account_id=account_id,
        has_active_device=bool(device),
        is_playing=bool(state.get("is_playing")),
        progress_ms=int(state.get("progress_ms") or 0),
        shuffle_state=bool(state.get("shuffle_state")),
        repeat_state=state.get("repeat_state") or "off",
        track=track,
        device=device,
    )


def _raise_api_error_from_spotify(exc: SpotifyAPIError) -> None:
    status_code = exc.status_code if 400 <= exc.status_code < 600 else status.HTTP_502_BAD_GATEWAY
    raise HTTPException(status_code=status_code, detail=exc.message)


@router.get("/player", response_model=SpotifyPlayerState)
async def get_player_state(
    account_id: UUID | None = Query(None, description="Spotify connected account id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyPlayerState:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, READ_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        state = await spotify.get_player_state()
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return _map_player_state(account.id, state)


@router.post("/player/play", response_model=SpotifyActionStatus)
async def play(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyActionStatus:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, MODIFY_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        await spotify.play()
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyActionStatus(status="ok")


@router.post("/player/pause", response_model=SpotifyActionStatus)
async def pause(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyActionStatus:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, MODIFY_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        await spotify.pause()
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyActionStatus(status="ok")


@router.post("/player/next", response_model=SpotifyActionStatus)
async def next_track(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyActionStatus:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, MODIFY_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        await spotify.next_track()
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyActionStatus(status="ok")


@router.post("/player/previous", response_model=SpotifyActionStatus)
async def previous_track(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyActionStatus:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, MODIFY_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        await spotify.previous_track()
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyActionStatus(status="ok")


@router.post("/player/volume", response_model=SpotifyActionStatus)
async def set_volume(
    percent: int = Query(..., ge=0, le=100, description="Volume percent 0-100"),
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyActionStatus:
    account = _get_spotify_account(db, current_user, account_id)
    _require_scopes(account, MODIFY_SCOPES)
    spotify = SpotifyService(db, account)
    try:
        await spotify.set_volume(percent)
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyActionStatus(status="ok")


@router.post("/transfer", response_model=SpotifyTransferSummary)
async def transfer_between_accounts(
    payload: SpotifyTransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpotifyTransferSummary:
    if payload.source_account_id == payload.destination_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination Spotify accounts must be different.",
        )

    if not (
        payload.transfer_playlists
        or payload.transfer_liked_songs
        or payload.transfer_saved_albums
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one transfer option.",
        )

    source_account = _get_spotify_account(db, current_user, payload.source_account_id)
    destination_account = _get_spotify_account(db, current_user, payload.destination_account_id)

    source_required_scopes: set[str] = set()
    destination_required_scopes: set[str] = set()

    if payload.transfer_playlists:
        source_required_scopes |= PLAYLIST_READ_SCOPES
        destination_required_scopes |= PLAYLIST_MODIFY_SCOPES

    if payload.transfer_liked_songs:
        source_required_scopes |= LIBRARY_READ_SCOPES
        destination_required_scopes |= LIBRARY_MODIFY_SCOPES

    if payload.transfer_saved_albums:
        source_required_scopes |= LIBRARY_READ_SCOPES
        destination_required_scopes |= LIBRARY_MODIFY_SCOPES

    _require_scopes(source_account, source_required_scopes)
    _require_scopes(destination_account, destination_required_scopes)

    transfer_service = SpotifyTransferService(db, source_account, destination_account)
    try:
        summary = await transfer_service.transfer(
            transfer_playlists=payload.transfer_playlists,
            transfer_liked_songs=payload.transfer_liked_songs,
            transfer_saved_albums=payload.transfer_saved_albums,
            only_owned_playlists=payload.only_owned_playlists,
        )
    except SpotifyAPIError as exc:
        _raise_api_error_from_spotify(exc)
    return SpotifyTransferSummary.model_validate(summary)
