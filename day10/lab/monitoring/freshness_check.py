"""Freshness checks for the Day 10 manifest."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _resolve_manifest_path(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        manifests = sorted(
            path.glob("manifest_*.json"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        return manifests[0] if manifests else None
    return None


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (status, detail) for the newest or provided manifest."""
    now = now or datetime.now(timezone.utc)
    resolved = _resolve_manifest_path(manifest_path)
    if resolved is None:
        return "FAIL", {"reason": "manifest_missing", "path": str(manifest_path)}

    data: Dict[str, Any] = json.loads(resolved.read_text(encoding="utf-8"))
    ts_raw = data.get("latest_exported_at") or data.get("run_timestamp")
    dt = parse_iso(str(ts_raw)) if ts_raw else None
    if dt is None:
        return "WARN", {
            "reason": "no_timestamp_in_manifest",
            "manifest": str(resolved),
            "run_id": data.get("run_id", ""),
        }

    freshness_hours = (now - dt).total_seconds() / 3600.0
    detail = {
        "status": "PASS" if freshness_hours <= sla_hours else "FAIL",
        "freshness_hours": round(freshness_hours, 3),
        "freshness_sla_hours": sla_hours,
        "last_successful_run_id": data.get("run_id", ""),
        "cleaned_records": data.get("cleaned_records", 0),
        "quarantine_records": data.get("quarantine_records", 0),
        "latest_exported_at": ts_raw,
        "manifest": str(resolved),
    }
    if freshness_hours <= sla_hours:
        return "PASS", detail
    return "FAIL", {**detail, "reason": "freshness_sla_exceeded"}
