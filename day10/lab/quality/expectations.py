"""Expectation suite for the Day 10 cleaned export."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
GRADING_QUESTIONS_PATH = ROOT / "data" / "grading_questions.json"


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _required_grading_doc_ids() -> list[str]:
    if not GRADING_QUESTIONS_PATH.is_file():
        return []
    items = json.loads(GRADING_QUESTIONS_PATH.read_text(encoding="utf-8"))
    required: list[str] = []
    seen: set[str] = set()
    for item in items:
        doc_id = (item.get("expect_top1_doc_id") or "").strip()
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            required.append(doc_id)
    return required


def _has_stale_content(row: Dict[str, Any]) -> bool:
    doc_id = (row.get("doc_id") or "").strip()
    text = _norm(str(row.get("chunk_text") or ""))
    if doc_id == "policy_refund_v4":
        return "14 ngay" in text or "14 ngay lam viec" in text
    if doc_id == "hr_leave_policy":
        return "10 ngay phep nam" in text
    return False


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """Return expectation results and whether the pipeline should halt."""
    results: List[ExpectationResult] = []

    # E1: at least one cleaned row survives.
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: all grading-critical doc_ids must remain present after cleaning.
    required_doc_ids = _required_grading_doc_ids()
    present_doc_ids = {
        str(row.get("doc_id", "")).strip() for row in cleaned_rows if row.get("doc_id")
    }
    missing_doc_ids = [doc_id for doc_id in required_doc_ids if doc_id not in present_doc_ids]
    results.append(
        ExpectationResult(
            "required_grading_sources_present",
            not missing_doc_ids,
            "halt",
            f"missing_doc_ids={missing_doc_ids}",
        )
    )

    # E3: stale refund / stale HR content must not survive cleaning.
    stale_rows = [row for row in cleaned_rows if _has_stale_content(row)]
    results.append(
        ExpectationResult(
            "no_stale_refund_or_hr_content",
            len(stale_rows) == 0,
            "halt",
            f"stale_rows={len(stale_rows)}",
        )
    )

    # E4: cleaned rows must have the metadata needed by later Day 9 integration.
    required_fields = (
        "chunk_id",
        "doc_id",
        "chunk_text",
        "effective_date",
        "exported_at",
        "title",
        "source_name",
        "source_system",
        "source_domain",
    )
    incomplete_rows = [
        row
        for row in cleaned_rows
        if any(not str(row.get(field, "")).strip() for field in required_fields)
    ]
    results.append(
        ExpectationResult(
            "metadata_completeness",
            len(incomplete_rows) == 0,
            "halt",
            f"incomplete_rows={len(incomplete_rows)}",
        )
    )

    # E5: chunk IDs should remain unique after deduplication.
    chunk_ids = [str(row.get("chunk_id", "")) for row in cleaned_rows if row.get("chunk_id")]
    duplicate_chunk_ids = len(chunk_ids) - len(set(chunk_ids))
    results.append(
        ExpectationResult(
            "unique_chunk_id",
            duplicate_chunk_ids == 0,
            "warn",
            f"duplicate_chunk_ids={duplicate_chunk_ids}",
        )
    )

    # E6: effective dates must be ISO after cleaning.
    iso_bad = [
        row
        for row in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("effective_date", "")).strip())
    ]
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            len(iso_bad) == 0,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    halt = any(not result.passed and result.severity == "halt" for result in results)
    return results, halt
