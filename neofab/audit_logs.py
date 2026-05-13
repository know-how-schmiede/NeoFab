from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import has_request_context, request


DEFAULT_LOG_FILE = "audit.log"


def get_log_root(app) -> Path:
    configured = app.config.get("NEOFAB_LOG_FOLDER")
    if configured:
        return Path(configured)
    return Path(app.root_path) / "logs"


def _day_folder(root: Path, timestamp: datetime) -> Path:
    return root / f"{timestamp.year:04d}" / f"{timestamp.month:02d}" / f"{timestamp.day:02d}"


def write_audit_log(
    app,
    event: str,
    user=None,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    """
    Append one structured audit entry.

    Files are stored as JSON lines below logs/YYYY/MM/DD/audit.log so more event
    types and levels can be added without changing the storage format.
    """
    try:
        now = datetime.utcnow()
        folder = _day_folder(get_log_root(app), now)
        folder.mkdir(parents=True, exist_ok=True)

        record: dict[str, Any] = {
            "timestamp_utc": now.isoformat(timespec="seconds") + "Z",
            "level": level,
            "event": event,
            "user_id": getattr(user, "id", None),
            "email": getattr(user, "email", "") or "",
            "role": getattr(user, "role", "") or "",
            "details": details or {},
        }

        if has_request_context():
            record["remote_addr"] = request.headers.get("X-Forwarded-For", request.remote_addr or "")
            record["user_agent"] = request.headers.get("User-Agent", "")

        log_path = folder / DEFAULT_LOG_FILE
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        app.logger.exception("Failed to write audit log entry for event %s", event)


def list_log_files(app) -> list[dict[str, Any]]:
    root = get_log_root(app)
    if not root.exists():
        return []

    files: list[dict[str, Any]] = []
    for path in root.rglob("*.log"):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    files.sort(key=lambda item: item["path"], reverse=True)
    return files


def read_log_entries(app, relative_path: str | None, max_entries: int = 500) -> tuple[str | None, list[dict[str, Any]]]:
    files = list_log_files(app)
    if not files:
        return None, []

    selected = relative_path or files[0]["path"]
    known_paths = {item["path"] for item in files}
    if selected not in known_paths:
        selected = files[0]["path"]

    root = get_log_root(app).resolve()
    log_path = (root / selected).resolve()
    if root not in log_path.parents:
        return files[0]["path"], []

    entries: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                entry = {"raw": raw}
            entries.append(entry)

    return selected, list(reversed(entries[-max_entries:]))


def delete_log_file(app, relative_path: str) -> bool:
    files = list_log_files(app)
    known_paths = {item["path"] for item in files}
    if relative_path not in known_paths:
        return False

    root = get_log_root(app).resolve()
    log_path = (root / relative_path).resolve()
    if root not in log_path.parents or not log_path.is_file():
        return False

    log_path.unlink()

    parent = log_path.parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent

    return True
