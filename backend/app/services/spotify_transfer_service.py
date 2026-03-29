"""Cross-account Spotify transfer service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ConnectedAccount
from app.services.spotify_service import SpotifyAPIError, SpotifyService

SPOTIFY_LIBRARY_WRITE_BATCH_SIZE = 40


class SpotifyTransferService:
    def __init__(
        self,
        db: Session,
        source_account: ConnectedAccount,
        destination_account: ConnectedAccount,
    ) -> None:
        self.db = db
        self.source_account = source_account
        self.destination_account = destination_account
        self.source = SpotifyService(db, source_account)
        self.destination = SpotifyService(db, destination_account)

    async def transfer(
        self,
        *,
        transfer_playlists: bool = True,
        transfer_liked_songs: bool = True,
        transfer_saved_albums: bool = True,
        only_owned_playlists: bool = True,
    ) -> dict[str, Any]:
        destination_profile = await self.destination.get_profile()
        destination_spotify_user_id = destination_profile.get("id")
        if not destination_spotify_user_id:
            raise SpotifyAPIError(
                status_code=502,
                message="Could not determine destination Spotify user id.",
            )

        report: dict[str, Any] = {
            "source_account_id": self.source_account.id,
            "destination_account_id": self.destination_account.id,
            "playlists_considered": 0,
            "playlists_copied": 0,
            "playlists_failed": 0,
            "playlist_tracks_transferred": 0,
            "liked_songs_transferred": 0,
            "saved_albums_transferred": 0,
            "warnings": [],
            "playlist_results": [],
        }

        if transfer_playlists:
            try:
                await self._transfer_playlists(
                    report=report,
                    only_owned_playlists=only_owned_playlists,
                )
            except SpotifyAPIError as exc:
                report["warnings"].append(f"Playlist transfer skipped: {exc.message}")

        if transfer_liked_songs:
            try:
                await self._transfer_liked_songs(report=report)
            except SpotifyAPIError as exc:
                report["warnings"].append(f"Liked songs transfer skipped: {exc.message}")

        if transfer_saved_albums:
            try:
                await self._transfer_saved_albums(report=report)
            except SpotifyAPIError as exc:
                report["warnings"].append(f"Saved albums transfer skipped: {exc.message}")

        return report

    async def _transfer_playlists(
        self,
        *,
        report: dict[str, Any],
        only_owned_playlists: bool,
    ) -> None:
        source_owner_id = self.source_account.provider_account_id
        playlists = await self._collect_playlists(
            source_owner_id=source_owner_id,
            only_owned_playlists=only_owned_playlists,
        )
        report["playlists_considered"] = len(playlists)

        for playlist in playlists:
            source_playlist_id = str(playlist.get("id") or "")
            source_playlist_name = str(playlist.get("name") or "Untitled Playlist")
            destination_playlist_id: str | None = None
            destination_playlist_name: str | None = None
            tracks_transferred = 0
            skipped_unavailable_tracks = 0
            status = "ok"
            warning: str | None = None

            try:
                if not source_playlist_id:
                    raise SpotifyAPIError(
                        status_code=422,
                        message="Playlist is missing id.",
                    )
                track_uris, skipped = await self._collect_playlist_track_uris(source_playlist_id)
                skipped_unavailable_tracks = skipped

                collaborative = bool(playlist.get("collaborative"))
                created = await self.destination.create_playlist(
                    name=source_playlist_name,
                    description=(playlist.get("description") or ""),
                    public=bool(playlist.get("public")) and not collaborative,
                    collaborative=collaborative,
                )
                destination_playlist_id = created.get("id")
                destination_playlist_name = created.get("name")

                for chunk in _chunks(track_uris, 100):
                    await self.destination.add_playlist_items(
                        playlist_id=str(destination_playlist_id),
                        uris=chunk,
                    )
                    tracks_transferred += len(chunk)

                report["playlists_copied"] += 1
                report["playlist_tracks_transferred"] += tracks_transferred
            except SpotifyAPIError as exc:
                status = "error"
                warning = exc.message
                report["playlists_failed"] += 1
                report["warnings"].append(
                    f"Playlist '{source_playlist_name}' failed: {exc.message}"
                )

            report["playlist_results"].append(
                {
                    "source_playlist_id": source_playlist_id,
                    "source_playlist_name": source_playlist_name,
                    "destination_playlist_id": destination_playlist_id,
                    "destination_playlist_name": destination_playlist_name,
                    "tracks_transferred": tracks_transferred,
                    "skipped_unavailable_tracks": skipped_unavailable_tracks,
                    "status": status,
                    "warning": warning,
                }
            )

    async def _transfer_liked_songs(self, *, report: dict[str, Any]) -> None:
        track_ids = await self._collect_liked_track_ids()
        unique_track_ids = _unique_preserve_order(track_ids)

        for chunk in _chunks(unique_track_ids, SPOTIFY_LIBRARY_WRITE_BATCH_SIZE):
            await self.destination.save_tracks(track_ids=chunk)
        report["liked_songs_transferred"] = len(unique_track_ids)

    async def _transfer_saved_albums(self, *, report: dict[str, Any]) -> None:
        album_ids = await self._collect_saved_album_ids()
        unique_album_ids = _unique_preserve_order(album_ids)

        for chunk in _chunks(unique_album_ids, SPOTIFY_LIBRARY_WRITE_BATCH_SIZE):
            await self.destination.save_albums(album_ids=chunk)
        report["saved_albums_transferred"] = len(unique_album_ids)

    async def _collect_playlists(
        self,
        *,
        source_owner_id: str,
        only_owned_playlists: bool,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self.source.list_playlists_page(limit=50, offset=offset)
            page_items = page.get("items") or []

            for playlist in page_items:
                owner_id = (playlist.get("owner") or {}).get("id")
                if only_owned_playlists and owner_id != source_owner_id:
                    continue
                items.append(playlist)

            if not page.get("next"):
                break
            offset += len(page_items)
            if not page_items:
                break

        return items

    async def _collect_playlist_track_uris(self, playlist_id: str) -> tuple[list[str], int]:
        uris: list[str] = []
        skipped = 0
        offset = 0

        while True:
            page = await self.source.list_playlist_tracks_page(
                playlist_id=playlist_id,
                limit=100,
                offset=offset,
            )
            page_items = page.get("items") or []
            for item in page_items:
                track = item.get("item") or item.get("track") or {}
                uri = track.get("uri")
                if isinstance(uri, str) and uri.startswith("spotify:track:"):
                    uris.append(uri)
                else:
                    skipped += 1

            if not page.get("next"):
                break
            offset += len(page_items)
            if not page_items:
                break

        return uris, skipped

    async def _collect_liked_track_ids(self) -> list[str]:
        track_ids: list[str] = []
        offset = 0

        while True:
            page = await self.source.list_saved_tracks_page(limit=50, offset=offset)
            page_items = page.get("items") or []
            for item in page_items:
                track_id = (item.get("track") or {}).get("id")
                if isinstance(track_id, str) and track_id:
                    track_ids.append(track_id)

            if not page.get("next"):
                break
            offset += len(page_items)
            if not page_items:
                break

        return track_ids

    async def _collect_saved_album_ids(self) -> list[str]:
        album_ids: list[str] = []
        offset = 0

        while True:
            page = await self.source.list_saved_albums_page(limit=50, offset=offset)
            page_items = page.get("items") or []
            for item in page_items:
                album_id = (item.get("album") or {}).get("id")
                if isinstance(album_id, str) and album_id:
                    album_ids.append(album_id)

            if not page.get("next"):
                break
            offset += len(page_items)
            if not page_items:
                break

        return album_ids


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
