"""Cleaning rules for the Day 10 raw export.

The raw CSV is intentionally noisy. This module keeps the pipeline focused on
four jobs:
1. validate source eligibility,
2. normalize dates and content,
3. remove stale or duplicate rows, and
4. emit deterministic chunk IDs and metadata for publishing.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple


ALLOWED_DOC_IDS = frozenset(
    {
        "access_control_sop",
        "hr_leave_policy",
        "it_helpdesk_faq",
        "policy_refund_v4",
        "sla_p1_2026",
    }
)

CANONICAL_SOURCE_META: dict[str, dict[str, str]] = {
    "access_control_sop": {
        "title": "Access Control SOP",
        "source_system": "access_control",
        "source_domain": "it_helpdesk",
    },
    "hr_leave_policy": {
        "title": "HR Leave Policy",
        "source_system": "hr_policy",
        "source_domain": "hr",
    },
    "it_helpdesk_faq": {
        "title": "IT Helpdesk FAQ",
        "source_system": "it_helpdesk",
        "source_domain": "it_helpdesk",
    },
    "policy_refund_v4": {
        "title": "Refund Policy v4",
        "source_system": "cs_refund",
        "source_domain": "cs_helpdesk",
    },
    "sla_p1_2026": {
        "title": "P1 SLA 2026",
        "source_system": "incident_management",
        "source_domain": "it_helpdesk",
    },
}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_YMD_SLASH = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")


def _norm_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").casefold().replace("đ", "d"))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def _bump(stats: dict[str, int], key: str, amount: int = 1) -> None:
    stats[key] = stats.get(key, 0) + amount


def _clean_text(text: str, stats: dict[str, int]) -> tuple[str, list[str]]:
    cleaned = (text or "").strip()
    flags: list[str] = []
    normalized = _norm_text(cleaned)

    if normalized.startswith("noi dung khong ro rang:"):
        cleaned = re.sub(r"^(?:!+\s*)?[^:]+:\s*", "", cleaned, count=1).strip()
        flags.append("stripped_noise_prefix")
        _bump(stats, "noise_prefixes_stripped")
    elif cleaned.lstrip().startswith("!!!"):
        cleaned = re.sub(r"^!+\s*", "", cleaned).strip()
        flags.append("stripped_noise_prefix")
        _bump(stats, "noise_prefixes_stripped")

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned:
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        deduped_sentences: list[str] = []
        for sentence in parts:
            sentence = sentence.strip()
            if not sentence:
                continue
            if deduped_sentences and _norm_text(deduped_sentences[-1]) == _norm_text(sentence):
                flags.append("collapsed_repeated_sentence")
                continue
            deduped_sentences.append(sentence)
        if deduped_sentences:
            cleaned = " ".join(deduped_sentences)

    return cleaned, flags


def _stable_chunk_id(doc_id: str, effective_date: str, chunk_text: str) -> str:
    digest = hashlib.sha256(
        f"{doc_id}|{effective_date}|{_norm_text(chunk_text)}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{doc_id}_{digest}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """Return (iso_date, error_reason)."""
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    m = _YMD_SLASH.match(s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def _quarantine(row: Dict[str, str], reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {**row, "reason": reason}
    payload.update(extra)
    return payload


def _build_cleaned_row(
    *,
    doc_id: str,
    chunk_text: str,
    effective_date: str,
    exported_at: str,
    source_path: str = "",
) -> Dict[str, Any]:
    meta = CANONICAL_SOURCE_META.get(doc_id, {})
    return {
        "chunk_id": _stable_chunk_id(doc_id, effective_date, chunk_text),
        "doc_id": doc_id,
        "chunk_text": chunk_text,
        "effective_date": effective_date,
        "exported_at": exported_at or "",
        "title": meta.get("title", doc_id),
        "source_name": meta.get("title", doc_id),
        "source_system": meta.get("source_system", "unknown"),
        "source_domain": meta.get("source_domain", "unknown"),
        "source_path": source_path or "",
    }


def _is_stale_refund(doc_id: str, text: str) -> bool:
    if doc_id != "policy_refund_v4":
        return False
    normalized = _norm_text(text)
    return "14 ngay" in normalized or "14 ngay lam viec" in normalized


def _is_stale_hr(doc_id: str, text: str, effective_date: str) -> bool:
    if doc_id != "hr_leave_policy":
        return False
    normalized = _norm_text(text)
    if effective_date < "2026-01-01":
        return True
    return "10 ngay phep nam" in normalized


def _deduplicate_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (row["doc_id"], _norm_text(str(row["chunk_text"])))
        current = best.get(key)
        if current is None:
            best[key] = row
            order.append(key)
            continue
        current_key = (
            str(current.get("effective_date", "")),
            str(current.get("exported_at", "")),
        )
        incoming_key = (
            str(row.get("effective_date", "")),
            str(row.get("exported_at", "")),
        )
        if incoming_key > current_key:
            best[key] = row
    deduped = [best[key] for key in order]
    return deduped, len(rows) - len(deduped)


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
    return_stats: bool = False,
) -> (
    Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]
    | Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]
):
    """Return cleaned rows, quarantined rows, and optional stats."""
    stats: dict[str, int] = {
        "raw_rows": len(rows),
        "kept_rows": 0,
        "quarantine_rows": 0,
        "unknown_doc_ids": 0,
        "missing_content_rows": 0,
        "normalized_dates": 0,
        "stale_refund_rows_removed": 0,
        "stale_hr_rows_removed": 0,
        "duplicate_rows_removed": 0,
        "noise_prefixes_stripped": 0,
    }
    quarantine: List[Dict[str, Any]] = []
    cleaned_candidates: List[Dict[str, Any]] = []

    for raw in rows:
        doc_id = (raw.get("doc_id") or "").strip()
        chunk_text_raw = raw.get("chunk_text") or ""
        effective_date_raw = raw.get("effective_date") or ""
        exported_at = (raw.get("exported_at") or "").strip()
        source_path = (raw.get("source_path") or "").strip()

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append(_quarantine(raw, "unknown_doc_id"))
            _bump(stats, "unknown_doc_ids")
            continue

        chunk_text, text_flags = _clean_text(chunk_text_raw, stats)
        if not chunk_text or len(chunk_text) < 8:
            quarantine.append(_quarantine(raw, "missing_chunk_text"))
            _bump(stats, "missing_content_rows")
            continue

        effective_date, date_error = _normalize_effective_date(effective_date_raw)
        if date_error == "empty_effective_date":
            quarantine.append(_quarantine(raw, "missing_effective_date"))
            _bump(stats, "missing_content_rows")
            continue
        if date_error:
            quarantine.append(
                _quarantine(
                    raw,
                    date_error,
                    effective_date_raw=effective_date_raw,
                )
            )
            continue
        if effective_date != effective_date_raw:
            _bump(stats, "normalized_dates")

        if _is_stale_refund(doc_id, chunk_text):
            quarantine.append(_quarantine(raw, "stale_refund_window"))
            _bump(stats, "stale_refund_rows_removed")
            continue

        if _is_stale_hr(doc_id, chunk_text, effective_date):
            quarantine.append(
                _quarantine(
                    raw,
                    "stale_hr_policy_effective_date",
                    effective_date_normalized=effective_date,
                )
            )
            _bump(stats, "stale_hr_rows_removed")
            continue

        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            # Keep the canonical 7-day wording on rows that are otherwise valid.
            if "14 ngay" in _norm_text(chunk_text):
                chunk_text = re.sub(
                    r"14\s+ngay\s+lam\s+viec",
                    "7 ngay lam viec",
                    _norm_text(chunk_text),
                )
                text_flags.append("refund_window_canonicalized")

        cleaned_candidates.append(
            {
                **_build_cleaned_row(
                    doc_id=doc_id,
                    chunk_text=chunk_text,
                    effective_date=effective_date,
                    exported_at=exported_at,
                    source_path=source_path,
                ),
                "cleaning_flags": json.dumps(sorted(set(text_flags)), ensure_ascii=False),
            }
        )

    deduped, duplicate_count = _deduplicate_rows(cleaned_candidates)
    if duplicate_count:
        _bump(stats, "duplicate_rows_removed", duplicate_count)

    cleaned = sorted(
        deduped,
        key=lambda item: (
            str(item.get("doc_id", "")),
            str(item.get("effective_date", "")),
            str(item.get("chunk_id", "")),
        ),
    )

    stats["kept_rows"] = len(cleaned)
    stats["quarantine_rows"] = len(quarantine)

    if return_stats:
        return cleaned, quarantine, stats
    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "chunk_id",
        "doc_id",
        "chunk_text",
        "effective_date",
        "exported_at",
        "title",
        "source_name",
        "source_system",
        "source_domain",
        "source_path",
        "cleaning_flags",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(
            "chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n",
            encoding="utf-8",
        )
        return
    keys: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
