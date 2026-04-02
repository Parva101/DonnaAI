"""Helpers around the local whatsapp_bridge proof-of-concept."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ConnectedAccount, User
from app.schemas.connected_account import ConnectedAccountCreate, ConnectedAccountUpdate
from app.services.connected_account_service import ConnectedAccountService


class WhatsAppBridgeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.account_svc = ConnectedAccountService(db)

        backend_dir = Path(__file__).resolve().parents[2]  # backend/
        repo_root = backend_dir.parent
        self.bridge_script = repo_root / "whatsapp_bridge" / "bridge.py"
        self.runtime_dir = (backend_dir / settings.whatsapp_bridge_runtime_dir).resolve()
        self.device_id = settings.whatsapp_bridge_device_id

        self.qr_dir = self.runtime_dir / "qr"
        self.logs_dir = self.runtime_dir / "logs"
        self.messages_log = self.logs_dir / "messages.jsonl"
        self.pid_file = self.runtime_dir / "bridge.pid"
        self.live_log = self.logs_dir / "bridge-live.log"
        self.state_file = self.runtime_dir / "bridge.state.json"
        self.start_lock_file = self.runtime_dir / "bridge.start.lock"

    def _ensure_runtime(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.qr_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _qr_png_path(self) -> Path:
        return self.qr_dir / f"{self.device_id}.png"

    def _qr_txt_path(self) -> Path:
        return self.qr_dir / f"{self.device_id}.txt"

    def _read_pid(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _is_pid_running(self, pid: int | None) -> bool:
        if not pid:
            return False
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return str(pid) in (out.stdout or "")
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _kill_pid(self, pid: int) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                os.kill(pid, 15)
        except Exception:
            pass

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _state_age_seconds(self, state: dict[str, Any] | None) -> float | None:
        if not state:
            return None
        raw = state.get("updated_at")
        if not isinstance(raw, str) or not raw:
            return None
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return max((datetime.now(timezone.utc) - ts).total_seconds(), 0.0)
        except Exception:
            return None

    def _acquire_start_lock(self, timeout_seconds: float = 8.0) -> int | None:
        """Best-effort cross-process lock to prevent duplicate listener starts."""
        deadline = time.time() + timeout_seconds
        while True:
            try:
                fd = os.open(
                    str(self.start_lock_file),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                )
                os.write(fd, str(os.getpid()).encode("utf-8"))
                return fd
            except FileExistsError:
                # Another request may be starting it; if bridge is already up, skip waiting.
                existing_pid = self._read_pid()
                if self._is_pid_running(existing_pid):
                    return None
                if time.time() >= deadline:
                    # Stale lock fallback.
                    try:
                        self.start_lock_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                time.sleep(0.2)

    def _release_start_lock(self, fd: int | None) -> None:
        if fd is None:
            return
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            self.start_lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def ensure_connected_account(self, user: User) -> ConnectedAccount:
        existing = self.account_svc.get_by_provider(
            user_id=user.id,
            provider="whatsapp",
            provider_account_id=self.device_id,
        )
        metadata = {
            "runtime_dir": str(self.runtime_dir),
            "device_id": self.device_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(account_metadata=metadata, account_email=self.device_id),
            )
        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="whatsapp",
                provider_account_id=self.device_id,
                account_email=self.device_id,
                access_token_encrypted=None,
                refresh_token_encrypted=None,
                token_expires_at=None,
                scopes=None,
                account_metadata=metadata,
            ),
        )

    def start_listener(self) -> dict[str, Any]:
        self._ensure_runtime()
        lock_fd = self._acquire_start_lock()
        try:
            pid = self._read_pid()
            if self._is_pid_running(pid):
                state = self._read_state()
                age = self._state_age_seconds(state)
                # If no bridge heartbeat for a while, recycle the listener process.
                if age is None or age <= 120:
                    return {"running": True, "pid": pid}
                self._kill_pid(pid)
                self.pid_file.unlink(missing_ok=True)

            with self.live_log.open("a", encoding="utf-8") as logf:
                proc = subprocess.Popen(  # noqa: S603
                    [
                        sys.executable,
                        str(self.bridge_script),
                        "--runtime-dir",
                        str(self.runtime_dir),
                        "--device-id",
                        self.device_id,
                        "listen",
                    ],
                    stdout=logf,
                    stderr=logf,
                    cwd=str(self.bridge_script.parent),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                )
            self.pid_file.write_text(str(proc.pid), encoding="utf-8")
            time.sleep(2)
            if not self._is_pid_running(proc.pid):
                details = ""
                if self.live_log.exists():
                    tail = self.live_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-5:]
                    details = " | ".join(tail)
                raise ValueError(
                    "WhatsApp bridge failed to start. "
                    "Check whatsapp_bridge dependencies and runtime logs."
                    + (f" Last log: {details}" if details else "")
                )
            return {"running": True, "pid": proc.pid}
        finally:
            self._release_start_lock(lock_fd)

    def status(self) -> dict[str, Any]:
        self._ensure_runtime()
        pid = self._read_pid()
        running = self._is_pid_running(pid)
        state = self._read_state()
        state_age_seconds = self._state_age_seconds(state)

        qr_png = self._qr_png_path()
        qr_txt = self._qr_txt_path()
        qr_data_uri = None
        if qr_png.exists():
            qr_data_uri = (
                "data:image/png;base64,"
                + base64.b64encode(qr_png.read_bytes()).decode("ascii")
            )

        qr_text = qr_txt.read_text(encoding="utf-8").strip() if qr_txt.exists() else None

        return {
            "running": running,
            "pid": pid if running else None,
            "device_id": self.device_id,
            "qr_data_uri": qr_data_uri,
            "qr_text": qr_text,
            "messages_log_exists": self.messages_log.exists(),
            "connection_state": state.get("status") if isinstance(state, dict) else None,
            "me_jid": state.get("me_jid") if isinstance(state, dict) else None,
            "state_updated_at": state.get("updated_at") if isinstance(state, dict) else None,
            "state_age_seconds": state_age_seconds,
        }

    def list_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.messages_log.exists():
            return []
        lines = self.messages_log.read_text(encoding="utf-8", errors="ignore").splitlines()
        rows = []
        for line in lines[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    @staticmethod
    def _parse_received_at(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _is_attachment_message(message_type: str | None) -> bool:
        kind = (message_type or "").strip().lower()
        return kind not in {"", "conversation", "extendedtextmessage", "senderkeydistributionmessage"}

    @staticmethod
    def _message_key(row: dict[str, Any]) -> str:
        message_id = (row.get("message_id") or "").strip()
        if message_id:
            return message_id
        return "|".join(
            [
                str(row.get("chat_jid") or ""),
                str(row.get("timestamp") or ""),
                str(row.get("sender_jid") or ""),
                str(row.get("text") or "")[:120],
            ]
        )

    def list_conversations(
        self,
        *,
        limit: int = 5000,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self.list_messages(limit=limit)
        grouped: dict[str, dict[str, Any]] = {}
        dedupe: dict[str, set[str]] = {}

        for row in rows:
            chat_jid = (row.get("chat_jid") or row.get("sender_jid") or "").strip()
            if not chat_jid:
                continue
            group = grouped.setdefault(
                chat_jid,
                {
                    "conversation_id": chat_jid,
                    "message_count": 0,
                    "unread_count": 0,
                    "latest_received_at": None,
                    "preview": None,
                    "latest_sender": None,
                    "latest_type": None,
                    "is_group": False,
                },
            )
            keys = dedupe.setdefault(chat_jid, set())
            msg_key = self._message_key(row)
            if msg_key in keys:
                continue
            keys.add(msg_key)

            group["message_count"] += 1
            from_me = bool(row.get("from_me"))
            if not from_me:
                group["unread_count"] += 1
            if bool(row.get("is_group")):
                group["is_group"] = True

            received_at = self._parse_received_at(row.get("received_at"))
            current_latest = group["latest_received_at"]
            if current_latest is None or (
                received_at is not None and received_at > current_latest
            ):
                group["latest_received_at"] = received_at
                group["preview"] = (row.get("text") or "").strip() or None
                group["latest_sender"] = (row.get("sender_jid") or "").strip() or None
                group["latest_type"] = row.get("message_type")

        search_lc = search.strip().lower() if search else None
        conversations: list[dict[str, Any]] = []
        for chat_jid, group in grouped.items():
            sender = group["latest_sender"] or chat_jid
            if group["is_group"]:
                sender = f"Group {chat_jid.split('@')[0]}"

            if unread_only and int(group["unread_count"] or 0) <= 0:
                continue

            if search_lc:
                blob = " ".join(
                    [
                        chat_jid.lower(),
                        str(sender).lower(),
                        str(group["preview"] or "").lower(),
                    ]
                )
                if search_lc not in blob:
                    continue

            conversations.append(
                {
                    "conversation_id": chat_jid,
                    "sender": sender,
                    "preview": group["preview"],
                    "unread_count": int(group["unread_count"] or 0),
                    "message_count": int(group["message_count"] or 0),
                    "has_attachments": self._is_attachment_message(group["latest_type"]),
                    "latest_received_at": group["latest_received_at"],
                    "is_group": bool(group["is_group"]),
                }
            )

        conversations.sort(
            key=lambda item: (
                item["latest_received_at"] is None,
                item["latest_received_at"] or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return conversations

    def list_conversation_messages(
        self,
        *,
        chat_jid: str,
        limit: int = 100,
        scan_limit: int = 5000,
    ) -> list[dict[str, Any]]:
        rows = self.list_messages(limit=scan_limit)
        deduped: dict[str, dict[str, Any]] = {}

        for row in rows:
            row_chat_jid = (row.get("chat_jid") or row.get("sender_jid") or "").strip()
            if row_chat_jid != chat_jid:
                continue

            key = self._message_key(row)
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = row
                continue

            existing_text = (existing.get("text") or "").strip()
            candidate_text = (row.get("text") or "").strip()
            if candidate_text and not existing_text:
                deduped[key] = row
                continue

            existing_received = self._parse_received_at(existing.get("received_at"))
            candidate_received = self._parse_received_at(row.get("received_at"))
            if (
                candidate_received is not None
                and (existing_received is None or candidate_received > existing_received)
            ):
                deduped[key] = row

        parsed_rows: list[dict[str, Any]] = []
        for row in deduped.values():
            parsed_rows.append(
                {
                    "message_id": row.get("message_id"),
                    "sender": "You" if row.get("from_me") else (row.get("sender_jid") or chat_jid),
                    "from_me": bool(row.get("from_me")),
                    "text": (row.get("text") or "").strip() or None,
                    "message_type": row.get("message_type"),
                    "timestamp": row.get("timestamp"),
                    "received_at": self._parse_received_at(row.get("received_at")),
                }
            )

        def _sort_key(item: dict[str, Any]) -> tuple:
            ts = item.get("timestamp")
            received_at = item.get("received_at")
            return (
                ts if isinstance(ts, int) else -1,
                received_at.timestamp() if isinstance(received_at, datetime) else -1.0,
            )

        parsed_rows.sort(key=_sort_key)
        return parsed_rows[-limit:]

    def send_message(self, to: str, text: str) -> dict[str, Any]:
        self._ensure_runtime()
        cmd = [
            sys.executable,
            str(self.bridge_script),
            "--runtime-dir",
            str(self.runtime_dir),
            "--device-id",
            self.device_id,
            "send",
            "--to",
            to,
            "--text",
            text,
            "--wait-after-send",
            "2",
        ]
        completed = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(self.bridge_script.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise ValueError(stderr or "Failed to send WhatsApp message")
        return {"status": "sent"}
