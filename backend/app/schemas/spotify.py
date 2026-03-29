from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SpotifyArtist(BaseModel):
    name: str


class SpotifyTrack(BaseModel):
    id: str | None = None
    name: str
    artists: list[SpotifyArtist]
    album_name: str | None = None
    album_image_url: str | None = None
    duration_ms: int | None = None
    external_url: str | None = None


class SpotifyDevice(BaseModel):
    id: str | None = None
    name: str
    type: str | None = None
    volume_percent: int | None = None
    is_active: bool = False
    is_restricted: bool = False


class SpotifyPlayerState(BaseModel):
    account_id: UUID
    has_active_device: bool = False
    is_playing: bool = False
    progress_ms: int = 0
    shuffle_state: bool = False
    repeat_state: str = "off"
    track: SpotifyTrack | None = None
    device: SpotifyDevice | None = None


class SpotifyActionStatus(BaseModel):
    status: str


class SpotifyTransferRequest(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    transfer_playlists: bool = True
    transfer_liked_songs: bool = True
    transfer_saved_albums: bool = True
    only_owned_playlists: bool = True


class SpotifyPlaylistTransferResult(BaseModel):
    source_playlist_id: str
    source_playlist_name: str
    destination_playlist_id: str | None = None
    destination_playlist_name: str | None = None
    tracks_transferred: int = 0
    skipped_unavailable_tracks: int = 0
    status: str = "ok"
    warning: str | None = None


class SpotifyTransferSummary(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    playlists_considered: int = 0
    playlists_copied: int = 0
    playlists_failed: int = 0
    playlist_tracks_transferred: int = 0
    liked_songs_transferred: int = 0
    saved_albums_transferred: int = 0
    warnings: list[str] = Field(default_factory=list)
    playlist_results: list[SpotifyPlaylistTransferResult] = Field(default_factory=list)
