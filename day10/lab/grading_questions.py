"""Validation helpers shared by grading CLI and the Day 10 demo API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from transform.cleaning_rules import ALLOWED_DOC_IDS

REQUIRED_FIELDS = (
    "id",
    "question",
    "must_contain_any",
    "must_not_contain",
    "expect_top1_doc_id",
    "grading_criteria",
)
LIST_FIELDS = ("must_contain_any", "must_not_contain", "grading_criteria")


class QuestionValidationError(ValueError):
    """Raised when a grading question file does not follow the contract."""


def validate_questions(
    payload: Any,
    *,
    available_doc_ids: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, list):
        raise QuestionValidationError("Question file must contain a JSON array.")
    if not payload:
        raise QuestionValidationError("Question list must contain at least one item.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    warnings: list[str] = []
    available = set(available_doc_ids or ALLOWED_DOC_IDS)

    for index, raw in enumerate(payload, start=1):
        prefix = f"Question #{index}"
        if not isinstance(raw, dict):
            raise QuestionValidationError(f"{prefix} must be a JSON object.")

        missing = [field for field in REQUIRED_FIELDS if field not in raw]
        if missing:
            raise QuestionValidationError(
                f"{prefix} is missing required fields: {', '.join(missing)}."
            )

        question_id = raw["id"]
        question = raw["question"]
        expected_doc_id = raw["expect_top1_doc_id"]
        if not isinstance(question_id, str) or not question_id.strip():
            raise QuestionValidationError(f"{prefix} field 'id' must be a non-empty string.")
        question_id = question_id.strip()
        if question_id in seen_ids:
            raise QuestionValidationError(f"Duplicate question id: {question_id}.")
        seen_ids.add(question_id)

        if not isinstance(question, str) or not question.strip():
            raise QuestionValidationError(
                f"Question '{question_id}' field 'question' must be a non-empty string."
            )
        if not isinstance(expected_doc_id, str) or not expected_doc_id.strip():
            raise QuestionValidationError(
                f"Question '{question_id}' field 'expect_top1_doc_id' "
                "must be a non-empty string."
            )

        clean_lists: dict[str, list[str]] = {}
        for field in LIST_FIELDS:
            value = raw[field]
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise QuestionValidationError(
                    f"Question '{question_id}' field '{field}' must be an array of strings."
                )
            clean_lists[field] = [item.strip() for item in value if item.strip()]

        expected_doc_id = expected_doc_id.strip()
        if expected_doc_id not in available:
            warnings.append(
                f"Question '{question_id}' expects doc_id '{expected_doc_id}', "
                "which is not present in the allowed/cleaned document set."
            )

        normalized.append(
            {
                "id": question_id,
                "question": question.strip(),
                "must_contain_any": clean_lists["must_contain_any"],
                "must_not_contain": clean_lists["must_not_contain"],
                "expect_top1_doc_id": expected_doc_id,
                "grading_criteria": clean_lists["grading_criteria"],
            }
        )

    return normalized, warnings


def load_and_validate_questions(
    path: Path,
    *,
    available_doc_ids: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        raise QuestionValidationError(f"Question file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuestionValidationError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return validate_questions(payload, available_doc_ids=available_doc_ids)
