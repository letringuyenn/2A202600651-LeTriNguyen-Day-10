"""FastAPI demo layer for the Day 10 data pipeline."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from grading_questions import (
    QuestionValidationError,
    load_and_validate_questions,
    validate_questions,
)
from monitoring.freshness_check import check_manifest_freshness

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
MANIFESTS = ARTIFACTS / "manifests"
EVAL_DIR = ARTIFACTS / "eval"
OFFICIAL_QUESTIONS = ROOT / "data" / "grading_questions.json"
CUSTOM_QUESTIONS = ROOT / "data" / "custom_grading_questions.json"
OFFICIAL_GRADING_OUTPUT = EVAL_DIR / "grading_run.jsonl"
UI_OFFICIAL_GRADING_OUTPUT = EVAL_DIR / "day10_ui_grading.jsonl"
CUSTOM_GRADING_OUTPUT = EVAL_DIR / "custom_grading_run.jsonl"
PIPELINE_TIMEOUT_SECONDS = 180
COMMAND_TIMEOUT_SECONDS = 120
_command_lock = threading.Lock()

app = FastAPI(
    title="Day 10 Data Pipeline & Observability Demo",
    version="1.0.0",
)


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _latest(directory: Path, pattern: str) -> Path | None:
    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_manifest_path() -> Path | None:
    return _latest(MANIFESTS, "manifest_*.json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _newest_existing(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def _question_path(mode: str) -> Path:
    if mode == "official":
        return OFFICIAL_QUESTIONS
    if mode == "custom":
        return CUSTOM_QUESTIONS
    raise HTTPException(status_code=400, detail="mode must be 'official' or 'custom'.")


def _grading_output_path(mode: str) -> Path | None:
    if mode == "official":
        return _newest_existing(
            [OFFICIAL_GRADING_OUTPUT, UI_OFFICIAL_GRADING_OUTPUT]
        )
    if mode == "custom":
        return CUSTOM_GRADING_OUTPUT
    raise HTTPException(status_code=400, detail="mode must be 'official' or 'custom'.")


def _read_grading(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "output_path": None,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "total_questions": 0,
            "passed_questions": 0,
            "top1_doc_matches_count": 0,
            "failed_ids": [],
            "rows": [],
        }

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    failed_ids: list[str] = []
    top1_matches = 0
    passed = 0
    for row in rows:
        top1_ok = row.get("top1_doc_matches") is not False
        contains_ok = row.get("contains_expected") is True
        forbidden_ok = row.get("hits_forbidden") is False
        row["passed"] = top1_ok and contains_ok and forbidden_ok
        if row.get("top1_doc_matches") is True:
            top1_matches += 1
        if row["passed"]:
            passed += 1
        else:
            failed_ids.append(str(row.get("id", "")))

    return {
        "output_path": _relative(path),
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "total_questions": len(rows),
        "passed_questions": passed,
        "top1_doc_matches_count": top1_matches,
        "failed_ids": failed_ids,
        "rows": rows,
    }


def _freshness_summary(manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        return {
            "status": "UNKNOWN",
            "freshness_hours": None,
            "freshness_sla_hours": float(os.environ.get("FRESHNESS_SLA_HOURS", "24")),
            "warning_only": True,
        }
    status, detail = check_manifest_freshness(
        manifest_path,
        sla_hours=float(os.environ.get("FRESHNESS_SLA_HOURS", "24")),
    )
    return {
        **detail,
        "status": status,
        "warning_only": status == "FAIL",
        "explanation": (
            "Freshness FAIL means the sample dataset is older than the SLA. "
            "This is an observability signal, not a pipeline quality failure."
        ),
    }


def _summary_payload() -> dict[str, Any]:
    manifest_path = _latest_manifest_path()
    if manifest_path is None:
        return {
            "ok": False,
            "error": "No manifest found. Run python etl_pipeline.py run first.",
        }

    manifest = _load_json(manifest_path)
    publish = manifest.get("publish") or {}
    grading_path = _grading_output_path("official")
    return {
        "ok": True,
        "latest_manifest": _relative(manifest_path),
        "run_id": manifest.get("run_id"),
        "run_timestamp": manifest.get("run_timestamp"),
        "quality_status": manifest.get("quality_status"),
        "raw_records": manifest.get("raw_records"),
        "cleaned_records": manifest.get("cleaned_records"),
        "quarantine_records": manifest.get("quarantine_records"),
        "publish_status": publish.get("status"),
        "upserted_ids": publish.get("upserted_ids"),
        "pruned_ids": publish.get("pruned_ids"),
        "cleaning_stats": manifest.get("cleaning_stats"),
        "quality_summary": manifest.get("quality_summary"),
        "grading": _read_grading(grading_path),
        "freshness": _freshness_summary(manifest_path),
    }


def _run_command(args: list[str], timeout: int) -> dict[str, Any]:
    if not _command_lock.acquire(blocking=False):
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Another Day 10 command is already running.",
        }

    try:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Command timed out after {timeout} seconds.\n{exc.stderr or ''}".strip(),
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"Could not start command: {exc}",
        }
    finally:
        _command_lock.release()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "day10_demo.html", media_type="text/html")


@app.get("/day10_styles.css", include_in_schema=False)
def styles() -> FileResponse:
    return FileResponse(ROOT / "day10_styles.css", media_type="text/css")


@app.get("/day10_app.js", include_in_schema=False)
def script() -> FileResponse:
    return FileResponse(ROOT / "day10_app.js", media_type="application/javascript")


@app.get("/README_PROJECT.md", include_in_schema=False)
def project_readme() -> FileResponse:
    return FileResponse(ROOT / "README_PROJECT.md", media_type="text/markdown")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "day10_web_demo"}


@app.get("/api/summary")
def summary() -> JSONResponse:
    payload = _summary_payload()
    return JSONResponse(payload, status_code=200 if payload["ok"] else 404)


@app.post("/api/run-pipeline")
def run_pipeline() -> dict[str, Any]:
    result = _run_command(["etl_pipeline.py", "run"], PIPELINE_TIMEOUT_SECONDS)
    result["summary"] = _summary_payload()
    return result


@app.post("/api/run-eval")
def run_eval() -> dict[str, Any]:
    output_path = EVAL_DIR / "day10_ui_eval.csv"
    result = _run_command(
        ["eval_retrieval.py", "--out", str(output_path.relative_to(ROOT))],
        COMMAND_TIMEOUT_SECONDS,
    )
    row_count = 0
    contains_expected_yes = 0
    hits_forbidden_no = 0
    if output_path.is_file():
        with output_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        row_count = len(rows)
        contains_expected_yes = sum(
            row.get("contains_expected", "").lower() == "yes" for row in rows
        )
        hits_forbidden_no = sum(
            row.get("hits_forbidden", "").lower() == "no" for row in rows
        )
    result["eval"] = {
        "output_path": _relative(output_path),
        "rows": row_count,
        "contains_expected_yes": contains_expected_yes,
        "hits_forbidden_no": hits_forbidden_no,
    }
    result["summary"] = _summary_payload()
    return result


@app.post("/api/run-grading")
def run_grading() -> dict[str, Any]:
    output_path = UI_OFFICIAL_GRADING_OUTPUT
    result = _run_command(
        ["grading_run.py", "--out", str(output_path.relative_to(ROOT))],
        COMMAND_TIMEOUT_SECONDS,
    )
    result["grading"] = _read_grading(output_path)
    result["summary"] = _summary_payload()
    return result


@app.get("/api/grading/questions")
def grading_questions(
    mode: str = Query(default="official", pattern="^(official|custom)$"),
) -> dict[str, Any]:
    path = _question_path(mode)
    try:
        questions, warnings = load_and_validate_questions(path)
    except QuestionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "ok": True,
        "mode": mode,
        "read_only": mode == "official",
        "path": _relative(path),
        "count": len(questions),
        "warnings": warnings,
        "questions": questions,
    }


@app.post("/api/grading/questions/custom")
def save_custom_grading_questions(
    payload: Any = Body(...),
) -> dict[str, Any]:
    try:
        questions, warnings = validate_questions(payload)
    except QuestionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    temp_path = CUSTOM_QUESTIONS.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(CUSTOM_QUESTIONS)
    return {
        "ok": True,
        "mode": "custom",
        "path": _relative(CUSTOM_QUESTIONS),
        "count": len(questions),
        "warnings": warnings,
        "questions": questions,
    }


@app.post("/api/run-custom-grading")
def run_custom_grading() -> dict[str, Any]:
    result = _run_command(
        [
            "grading_run.py",
            "--questions",
            str(CUSTOM_QUESTIONS.relative_to(ROOT)),
            "--out",
            str(CUSTOM_GRADING_OUTPUT.relative_to(ROOT)),
        ],
        COMMAND_TIMEOUT_SECONDS,
    )
    grading = _read_grading(CUSTOM_GRADING_OUTPUT)
    result["grading"] = grading
    result["total"] = grading["total"]
    result["passed"] = grading["passed"]
    result["failed"] = grading["failed"]
    result["failed_ids"] = grading["failed_ids"]
    result["output_path"] = grading["output_path"]
    return result


@app.get("/api/grading/results")
def grading_results(
    mode: str = Query(default="custom", pattern="^(official|custom)$"),
) -> dict[str, Any]:
    path = _grading_output_path(mode)
    grading = _read_grading(path)
    return {
        "ok": path is not None and path.is_file(),
        "mode": mode,
        **grading,
    }


@app.post("/api/run-freshness")
def run_freshness() -> dict[str, Any]:
    manifest_path = _latest_manifest_path()
    if manifest_path is None:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "No manifest found. Run python etl_pipeline.py run first.",
        }

    result = _run_command(
        [
            "etl_pipeline.py",
            "freshness",
            "--manifest",
            str(manifest_path.relative_to(ROOT)),
        ],
        COMMAND_TIMEOUT_SECONDS,
    )
    freshness = _freshness_summary(manifest_path)
    result["command_ok"] = result["ok"]
    result["ok"] = result["returncode"] in {0, 1}
    result["freshness"] = freshness
    result["observability_warning"] = freshness["status"] == "FAIL"
    result["summary"] = _summary_payload()
    return result


@app.get("/api/artifacts")
def artifacts() -> dict[str, Any]:
    grading_path = _grading_output_path("official")
    return {
        "ok": True,
        "artifacts": {
            "latest_manifest": _relative(_latest_manifest_path()),
            "latest_quarantine": _relative(
                _latest(ARTIFACTS / "quarantine", "quarantine_*.csv")
            ),
            "latest_eval": _relative(_latest(EVAL_DIR, "*.csv")),
            "grading_jsonl": _relative(grading_path),
            "custom_grading_jsonl": _relative(
                CUSTOM_GRADING_OUTPUT if CUSTOM_GRADING_OUTPUT.is_file() else None
            ),
            "latest_cleaned": _relative(
                _latest(ARTIFACTS / "cleaned", "cleaned_*.csv")
            ),
        },
    }
