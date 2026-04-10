"""Reusable OpenClaw gateway client for Donna channel integrations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings


class OpenClawGatewayClient:
    _MIN_NODE_VERSION = (22, 12, 0)
    _GATEWAY_START_TIMEOUT_SECONDS = 45.0
    _gateway_lock = threading.Lock()
    _gateway_process: subprocess.Popen[Any] | None = None

    def __init__(
        self,
        *,
        channel: str,
        account_id: str | None = None,
    ) -> None:
        backend_dir = Path(__file__).resolve().parents[2]
        repo_root = backend_dir.parent

        self.channel = (channel or "").strip().lower()
        self.account_id = (account_id or "").strip() or None

        self.cli_path = (settings.openclaw_cli_path or "openclaw").strip() or "openclaw"
        self.node_path = (settings.openclaw_node_path or "").strip()
        self.profile = settings.openclaw_profile.strip() or None
        self.gateway_url = settings.openclaw_gateway_url.strip() or None
        self.gateway_token = settings.openclaw_gateway_token.strip() or None
        self.gateway_password = settings.openclaw_gateway_password.strip() or None
        self.gateway_timeout_ms = max(int(settings.openclaw_gateway_timeout_ms), 1_000)
        if not self.gateway_token and not self.gateway_password:
            local_auth = self._read_local_gateway_auth()
            if local_auth is not None:
                token, password = local_auth
                self.gateway_token = token or None
                self.gateway_password = password or None

        configured_workdir = settings.openclaw_workdir.strip()
        self.workdir = Path(configured_workdir).resolve() if configured_workdir else repo_root
        self._resolved_cli_executable: str | None = None
        self._resolved_node_executable: str | None = None

    @staticmethod
    def _read_local_gateway_auth() -> tuple[str | None, str | None] | None:
        cfg_path = Path.home() / ".openclaw" / "openclaw.json"
        if not cfg_path.exists():
            return None
        try:
            # openclaw.json on Windows can include UTF-8 BOM.
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        gateway = data.get("gateway")
        if not isinstance(gateway, dict):
            return None
        auth = gateway.get("auth")
        if not isinstance(auth, dict):
            return None
        mode = str(auth.get("mode") or "").strip().lower()
        token = auth.get("token")
        password = auth.get("password")
        if mode == "token" and isinstance(token, str) and token.strip():
            return token.strip(), None
        if mode == "password" and isinstance(password, str) and password.strip():
            return None, password.strip()
        return None

    def _resolve_cli_executable(self) -> str:
        if self._resolved_cli_executable:
            return self._resolved_cli_executable
        candidate = Path(self.cli_path).expanduser()
        if candidate.exists():
            self._resolved_cli_executable = str(candidate)
            return self._resolved_cli_executable
        resolved = shutil.which(self.cli_path)
        if resolved:
            self._resolved_cli_executable = resolved
            return self._resolved_cli_executable
        # Graceful Docker/host fallback: if OPENCLAW_CLI_PATH is machine-specific and
        # invalid in this runtime, try the default executable name on PATH.
        fallback = shutil.which("openclaw")
        if fallback:
            self._resolved_cli_executable = fallback
            return self._resolved_cli_executable
        raise ValueError(
            "OpenClaw CLI not found. Set OPENCLAW_CLI_PATH to the openclaw executable path."
        )

    @staticmethod
    def _parse_node_version(output: str) -> tuple[int, int, int] | None:
        match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", (output or "").strip())
        if not match:
            return None
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    @classmethod
    def _version_gte(
        cls, version: tuple[int, int, int], minimum: tuple[int, int, int] | None = None
    ) -> bool:
        return version >= (minimum or cls._MIN_NODE_VERSION)

    @staticmethod
    def _resolve_openclaw_script(cli_executable: str) -> Path | None:
        cli_path = Path(cli_executable)
        candidates: list[Path] = []

        if cli_path.suffix.lower() == ".mjs" and cli_path.exists():
            return cli_path

        # Windows global npm installs can resolve to openclaw, openclaw.cmd, or openclaw.ps1.
        if cli_path.name.lower().startswith("openclaw"):
            candidates.extend(
                [
                    cli_path.parent / "openclaw.mjs",
                    cli_path.parent / "node_modules" / "openclaw" / "openclaw.mjs",
                ]
            )

        if cli_path.suffix.lower() in {".ps1", ".cmd", ".bat"}:
            candidates.append(cli_path.parent / "node_modules" / "openclaw" / "openclaw.mjs")

        for script in candidates:
            if script.exists():
                return script
        return None

    def _resolve_node_executable(self) -> str:
        if self._resolved_node_executable:
            return self._resolved_node_executable

        cli_executable = self._resolve_cli_executable()
        candidates: list[str] = []

        if self.node_path:
            candidates.append(str(Path(self.node_path).expanduser()))

        cli_dir_node = str(Path(cli_executable).parent / "node.exe")
        if Path(cli_dir_node).exists():
            candidates.append(cli_dir_node)

        default_node = Path(r"C:\Program Files\nodejs\node.exe")
        if os.name == "nt" and default_node.exists():
            candidates.append(str(default_node))

        resolved_node = shutil.which("node")
        if resolved_node:
            candidates.append(resolved_node)

        unique_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate.strip())

        tested: list[tuple[str, str]] = []
        for candidate in unique_candidates:
            try:
                completed = subprocess.run(  # noqa: S603
                    [candidate, "-v"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=3,
                )
            except Exception:
                continue

            output = (completed.stdout or completed.stderr or "").strip()
            version = self._parse_node_version(output)
            if completed.returncode == 0 and version and self._version_gte(version):
                self._resolved_node_executable = candidate
                return candidate
            tested.append((candidate, output))

        details = "; ".join(
            f"{path} -> {result or 'unavailable'}"
            for path, result in tested[:5]
        )
        hint = (
            "Set OPENCLAW_NODE_PATH to a Node.js v22.12+ executable "
            "(for example: C:\\Program Files\\nodejs\\node.exe)."
        )
        if details:
            raise ValueError(
                f"OpenClaw requires Node.js v22.12+ but no compatible runtime was found. "
                f"Tried: {details}. {hint}"
            )
        raise ValueError(
            f"OpenClaw requires Node.js v22.12+ but no Node executable was found. {hint}"
        )

    def _build_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        try:
            node_executable = self._resolve_node_executable()
        except ValueError:
            return env

        node_dir = str(Path(node_executable).parent)
        current_path = env.get("PATH", "")
        if current_path:
            env["PATH"] = node_dir + os.pathsep + current_path
        else:
            env["PATH"] = node_dir
        return env

    def _build_openclaw_prefix(self) -> list[str]:
        cli_executable = self._resolve_cli_executable()
        script_path = self._resolve_openclaw_script(cli_executable)
        if script_path is not None:
            return [self._resolve_node_executable(), str(script_path)]
        return [cli_executable]

    def _build_gateway_command(self, *, method: str, params: dict[str, Any]) -> list[str]:
        cmd = self._build_openclaw_prefix()
        if self.profile:
            cmd.extend(["--profile", self.profile])
        cmd.extend(
            [
                "gateway",
                "call",
                method,
                "--params",
                json.dumps(params, ensure_ascii=True),
                "--json",
            ]
        )
        if self.gateway_url:
            cmd.extend(["--url", self.gateway_url])
            if self.gateway_token:
                cmd.extend(["--token", self.gateway_token])
            elif self.gateway_password:
                cmd.extend(["--password", self.gateway_password])
        else:
            if self.gateway_token:
                cmd.extend(["--token", self.gateway_token])
            elif self.gateway_password:
                cmd.extend(["--password", self.gateway_password])
        return cmd

    def _probe_gateway(self, *, timeout_seconds: float = 3.0) -> tuple[bool, str]:
        cmd = self._build_gateway_command(method="health", params={})
        try:
            completed = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(self.workdir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=max(timeout_seconds, 1.0),
                env=self._build_subprocess_env(),
            )
        except Exception as exc:
            return False, str(exc)
        if completed.returncode == 0:
            return True, ""
        details = (completed.stderr or completed.stdout or "").strip()
        return False, details

    @classmethod
    def _gateway_process_running(cls) -> bool:
        process = cls._gateway_process
        return process is not None and process.poll() is None

    def _start_local_gateway(self) -> tuple[bool, str]:
        cmd = self._build_openclaw_prefix()
        if self.profile:
            cmd.extend(["--profile", self.profile])
        cmd.extend(["gateway", "run", "--dev", "--allow-unconfigured", "--ws-log", "compact"])

        runtime_dir = (self.workdir / ".runtime" / "openclaw").resolve()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        gateway_log = runtime_dir / "gateway-supervisor.log"
        with gateway_log.open("a", encoding="utf-8") as logf:
            process = subprocess.Popen(  # noqa: S603
                cmd,
                cwd=str(self.workdir),
                stdout=logf,
                stderr=logf,
                env=self._build_subprocess_env(),
            )
        self.__class__._gateway_process = process
        return True, str(gateway_log)

    def _ensure_local_gateway(self) -> None:
        # Explicit remote gateway URL means caller manages availability.
        if self.gateway_url:
            return

        ok, details = self._probe_gateway(timeout_seconds=6.0)
        if ok:
            return
        if "timed out" in (details or "").lower():
            return

        with self.__class__._gateway_lock:
            ok, details = self._probe_gateway(timeout_seconds=6.0)
            if ok:
                return
            if "timed out" in (details or "").lower():
                return

            if not self.__class__._gateway_process_running():
                _, log_path = self._start_local_gateway()
            else:
                log_path = str((self.workdir / ".runtime" / "openclaw" / "gateway-supervisor.log").resolve())

            deadline = time.monotonic() + self._GATEWAY_START_TIMEOUT_SECONDS
            last_error = details
            while time.monotonic() < deadline:
                ok, details = self._probe_gateway(timeout_seconds=6.0)
                if ok:
                    return
                last_error = details or last_error
                if not self.__class__._gateway_process_running():
                    break
                time.sleep(0.5)

            if "timed out" in (last_error or "").lower():
                return
            raise ValueError(
                "OpenClaw gateway is unavailable and auto-start failed. "
                f"Check {log_path}. Last error: {last_error or 'unknown error'}"
            )

    def ensure_channel_account(self) -> None:
        if not self.channel:
            return

        account = self.account_id or "default"
        cmd = self._build_openclaw_prefix()
        if self.profile:
            cmd.extend(["--profile", self.profile])
        cmd.extend(
            [
                "channels",
                "add",
                "--channel",
                self.channel,
                "--account",
                account,
            ]
        )
        completed = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(self.workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
            env=self._build_subprocess_env(),
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            raise ValueError(
                details
                or f"Failed to add OpenClaw channel `{self.channel}` account `{account}`."
            )

    @staticmethod
    def _parse_gateway_json(output: str) -> Any:
        raw = output.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            for line in reversed(raw.splitlines()):
                text = line.strip()
                if not text:
                    continue
                if not (text.startswith("{") or text.startswith("[")):
                    continue
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        raise ValueError("Gateway returned non-JSON output.")

    @staticmethod
    def _format_gateway_error(err: Any) -> str:
        if isinstance(err, str):
            return err
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str) and message.strip():
                return message
            code = err.get("code")
            if isinstance(code, str) and code.strip():
                return code
            return json.dumps(err, ensure_ascii=False)
        return str(err)

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> Any:
        self._ensure_local_gateway()
        cmd = self._build_gateway_command(method=method, params=params or {})
        timeout_seconds = (timeout_ms or self.gateway_timeout_ms) / 1_000
        try:
            completed = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(self.workdir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout_seconds,
                env=self._build_subprocess_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"OpenClaw gateway call timed out after {timeout_seconds:.1f}s.") from exc
        except FileNotFoundError as exc:
            raise ValueError(
                "OpenClaw CLI was not found. Set OPENCLAW_CLI_PATH correctly and retry."
            ) from exc

        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            raise ValueError(details or f"OpenClaw gateway call failed for method `{method}`.")

        parsed = self._parse_gateway_json(completed.stdout or "")
        if isinstance(parsed, dict) and parsed.get("ok") is False and "error" in parsed:
            raise ValueError(self._format_gateway_error(parsed.get("error")))
        return parsed

    @staticmethod
    def to_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(float(text))
            except ValueError:
                return None
        return None

    @staticmethod
    def datetime_from_ms(ms: int | None) -> datetime | None:
        if ms is None:
            return None
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except Exception:
            return None

    @staticmethod
    def iso_from_ms(ms: int | None) -> str | None:
        dt = OpenClawGatewayClient.datetime_from_ms(ms)
        return dt.isoformat() if dt else None

    @staticmethod
    def extract_text_from_message(message: dict[str, Any]) -> str | None:
        text = message.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        content = message.get("content")
        if isinstance(content, str):
            stripped = content.strip()
            return stripped or None

        if isinstance(content, list):
            chunks: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip().lower()
                if block_type == "text":
                    block_text = block.get("text")
                    if isinstance(block_text, str) and block_text.strip():
                        chunks.append(block_text.strip())
                    continue
                if block_type:
                    chunks.append(f"[{block_type}]")
            joined = "\n".join(chunks).strip()
            return joined or None

        return None

    def _session_matches_channel(self, row: dict[str, Any]) -> bool:
        if not self.channel:
            return True
        candidates = [
            row.get("channel"),
            row.get("lastChannel"),
        ]
        delivery = row.get("deliveryContext")
        if isinstance(delivery, dict):
            candidates.append(delivery.get("channel"))
        lowered = [str(item or "").strip().lower() for item in candidates if item is not None]
        return self.channel in lowered

    def _session_matches_account(self, row: dict[str, Any]) -> bool:
        if not self.account_id:
            return True
        last_account = str(row.get("lastAccountId") or "").strip()
        if last_account and last_account == self.account_id:
            return True
        delivery = row.get("deliveryContext")
        if isinstance(delivery, dict):
            delivery_account = str(delivery.get("accountId") or "").strip()
            if delivery_account and delivery_account == self.account_id:
                return True
        # Keep rows with missing account metadata visible to avoid accidental drops.
        return not last_account

    def list_sessions(
        self,
        *,
        limit: int = 200,
        search: str | None = None,
        include_last_message: bool = True,
        include_derived_titles: bool = True,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": max(int(limit), 1),
            "includeLastMessage": include_last_message,
            "includeDerivedTitles": include_derived_titles,
        }
        search_text = (search or "").strip()
        if search_text:
            params["search"] = search_text

        payload = self.call("sessions.list", params)
        sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
        rows: list[dict[str, Any]] = []
        for row in sessions:
            if not isinstance(row, dict):
                continue
            if not self._session_matches_channel(row):
                continue
            if not self._session_matches_account(row):
                continue
            rows.append(row)
        return rows

    def channel_snapshot(self, *, probe: bool = True) -> dict[str, Any] | None:
        payload = self.call(
            "channels.status",
            {
                "probe": bool(probe),
                "timeoutMs": min(self.gateway_timeout_ms, 15_000),
            },
            timeout_ms=max(self.gateway_timeout_ms, 15_000),
        )
        if not isinstance(payload, dict):
            return None

        channels = payload.get("channels")
        channel_row: dict[str, Any] | None = None
        if isinstance(channels, dict):
            row = channels.get(self.channel)
            if isinstance(row, dict):
                channel_row = row

        accounts_map = payload.get("channelAccounts")
        if isinstance(accounts_map, dict):
            entries = accounts_map.get(self.channel)
            if isinstance(entries, list):
                normalized = [row for row in entries if isinstance(row, dict)]
                if normalized:
                    if self.account_id:
                        for row in normalized:
                            if str(row.get("accountId") or "").strip() == self.account_id:
                                return row
                    default_map = payload.get("channelDefaultAccountId")
                    if isinstance(default_map, dict):
                        default_account = str(default_map.get(self.channel) or "").strip()
                        if default_account:
                            for row in normalized:
                                if str(row.get("accountId") or "").strip() == default_account:
                                    return row
                    return normalized[0]

        return channel_row

    def chat_history(self, *, session_key: str, limit: int = 100) -> list[dict[str, Any]]:
        payload = self.call(
            "chat.history",
            {
                "sessionKey": session_key,
                "limit": max(min(limit, 1000), 1),
            },
        )
        return payload.get("messages", []) if isinstance(payload, dict) else []

    def chat_send(self, *, session_key: str, text: str) -> dict[str, Any]:
        payload = self.call(
            "chat.send",
            {
                "sessionKey": session_key,
                "message": text,
                "deliver": True,
                "idempotencyKey": str(uuid4()),
            },
        )
        return payload if isinstance(payload, dict) else {}

    def raw_send(self, *, to: str, text: str) -> dict[str, Any]:
        payload = self.call(
            "send",
            {
                "channel": self.channel,
                "accountId": self.account_id,
                "to": to,
                "message": text,
                "idempotencyKey": str(uuid4()),
            },
        )
        return payload if isinstance(payload, dict) else {}
