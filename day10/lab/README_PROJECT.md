# Day 10 - Data Pipeline & Observability Project

## 1. Project Overview

This project completes the data layer that supports the previous AI engineering
labs:

- Day 8 created grounded Retrieval-Augmented Generation (RAG).
- Day 9 created a supervisor-worker multi-agent workflow.
- Day 10 creates the data pipeline that ensures information entering retrieval
  and multi-agent systems is clean, validated, version-aware, and observable.

Day 10 is deliberately isolated from the Day 8 retriever and Day 9 supervisor.
Its output is a validated, RAG-ready Chroma collection plus evidence artifacts
for quality, grading, quarantine, and freshness.

## 2. Problem

The raw policy export contains realistic data quality problems:

- duplicate records and repeated sync output;
- missing or whitespace-only content;
- stale refund policy text using a 14-day window instead of 7 days;
- stale HR leave policy text using 10 days instead of the 2026 value;
- non-ISO effective dates;
- unknown, invalid, and legacy document IDs;
- noisy prefixes and conflicting document versions.

Without cleaning and validation, a RAG system or agent can retrieve an obsolete
policy even when its model and prompt are working correctly.

## 3. Architecture

```text
data/raw/policy_export_dirty.csv
  -> transform/cleaning_rules.py
  -> quality/expectations.py
  -> artifacts/cleaned/
  -> Chroma day10_kb
  -> eval_retrieval.py / grading_run.py
  -> monitoring/freshness_check.py
  -> day10_web_demo.py UI
```

The ETL command reads the complete raw snapshot, quarantines invalid records,
halts on critical expectation failures, publishes stable chunk IDs to Chroma,
prunes stale vector IDs, and writes a run manifest.

## 4. Important Files

| File or directory | Purpose |
| --- | --- |
| `etl_pipeline.py` | Runs ingest, cleaning, validation, Chroma publish, manifest generation, and freshness logging. |
| `transform/cleaning_rules.py` | Canonical source allowlist, content cleanup, stale-policy filtering, date normalization, deduplication, and quarantine logic. |
| `quality/expectations.py` | Critical and warning-level data quality expectations. |
| `monitoring/freshness_check.py` | Compares the latest exported data timestamp with the freshness SLA. |
| `retrieval_embedding.py` | Deterministic local embedding function used by the lab and demo. |
| `eval_retrieval.py` | Runs retrieval evaluation and writes CSV evidence. |
| `grading_run.py` | Runs the ten grading questions and writes JSONL evidence. |
| `contracts/data_contract.yaml` | Canonical sources, metadata contract, ownership, and freshness SLA. |
| `artifacts/manifests/` | Per-run summary, quality, cleaning, and publish metadata. |
| `artifacts/quarantine/` | Records excluded from the clean snapshot, with reasons. |
| `artifacts/eval/` | Retrieval and grading outputs. |
| `day10_web_demo.py` | FastAPI routes for UI, pipeline actions, summaries, and artifacts. |
| `day10_demo.html` | Demo page structure. |
| `day10_app.js` | API calls, loading states, cards, metrics, logs, and grading table. |
| `day10_styles.css` | Responsive demo styling. |
| `run_day10_web_demo.py` | Local uvicorn launcher. |

## 5. Setup

Windows PowerShell:

```powershell
cd day10/lab
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The runtime uses paths relative to `day10/lab`; no machine-specific absolute
path is required.

## 6. Run Pipeline

```powershell
.venv\Scripts\python.exe etl_pipeline.py run
```

The command generates new cleaned, quarantine, log, and manifest artifacts.
Artifacts should be regenerated with commands rather than edited manually.

## 7. Run Eval

```powershell
.venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
```

This evaluates retrieval against `data/test_questions.json` and records top-1
documents, expected content coverage, and forbidden content hits.

## 8. Run Grading

```powershell
.venv\Scripts\python.exe grading_run.py --out artifacts/eval/grading_run.jsonl
```

Optional instructor verification:

```powershell
.venv\Scripts\python.exe instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```

## 9. Run Freshness Check

Use the latest manifest:

```powershell
$manifest = Get-ChildItem artifacts\manifests\manifest_*.json |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
.venv\Scripts\python.exe etl_pipeline.py freshness --manifest $manifest.FullName
```

The web demo resolves the latest manifest automatically. A freshness exit code
of 1 means the sample export is older than its SLA; it does not mean ETL quality
or publishing failed.

## 10. Run Web Demo

```powershell
.venv\Scripts\python.exe run_day10_web_demo.py
```

Open:

```text
http://127.0.0.1:8000
```

The UI can refresh the latest summary, run ETL, run retrieval evaluation, run
grading, run freshness checks, show command output, and list generated
artifacts.

## 11. Result Summary

Validated baseline:

```text
raw_records=247
cleaned_records=35
quarantine_records=160
quality_status=PASS
publish_status=OK
upserted_ids=35
grading=10/10 passed
freshness=FAIL because sample exported_at is older than SLA
```

Freshness is intentionally reported as an observability warning. The pipeline
still exits 0 after successful cleaning, validation, and publish.

## 12. Cleaning Rules Added

- `access_control_sop` is retained as a legitimate grading source.
- Unknown, invalid, and legacy document IDs are quarantined.
- Missing or invalid content is quarantined.
- Stale 14-day refund policy content is removed.
- Stale HR leave policy content is removed.
- Non-ISO effective dates are normalized where possible.
- Duplicate records are removed using stable document identity.
- Noise prefixes are stripped while preserving meaningful policy text.

The current run reports measurable counts in `manifest.cleaning_stats`.

## 13. Expectations Added

- `required_grading_sources_present`
- `no_stale_refund_or_hr_content`
- `metadata_completeness`
- `effective_date_iso_yyyy_mm_dd`
- `unique_chunk_id`

Critical expectations halt the pipeline before Chroma publish.

## 14. How Day 10 Connects to Day 8/9

Day 8 retrieval quality depends on the correctness of indexed data. Day 9
workers depend on retrieval when answering policy questions. Day 10 provides
the clean and observable data foundation that those systems can consume.

Direct Day 9 integration is intentionally deferred. No Day 8 retriever,
generation code, Day 9 supervisor, trace format, web demo, or UI is modified by
this project.

## 15. Known Limitations

- Freshness currently fails because the educational sample dataset is older
  than the configured SLA.
- The Day 9 retrieval adapter has not yet been integrated.
- This is an educational lab rather than a production orchestration platform.
- Chroma and deterministic local embeddings are used for repeatable lab/demo
  execution.
- The FastAPI command runner is intended for local demonstration and allows one
  pipeline-related command at a time.

## 16. Demo Script

Three-minute walkthrough:

1. Open `http://127.0.0.1:8000`.
2. Show the raw, cleaned, and quarantine record cards.
3. Refresh the summary or run the ETL pipeline.
4. Run grading and show the 10/10 result plus top-1 document matches.
5. Run freshness and explain that FAIL is an observability warning for old
   sample data.
6. Conclude with the principle: debug data before debugging the model.

## 17. Custom Grading Questions

The official benchmark remains:

```text
data/grading_questions.json
```

It is read-only from the web UI and remains the default when `grading_run.py`
is called without `--questions`.

Experimental questions are stored separately:

```text
data/custom_grading_questions.json
```

Run custom grading from PowerShell:

```powershell
.venv\Scripts\python.exe grading_run.py `
  --questions data/custom_grading_questions.json `
  --out artifacts/eval/custom_grading_run.jsonl
```

Run it from the UI:

1. Open the Day 10 Web Demo.
2. Go to **Custom Grading Lab**.
3. Select or load **Custom grading**.
4. Add or edit questions in the form.
5. Apply the form entry to the local list, then select **Save custom questions**.
6. Select **Run custom grading** and inspect the per-question result table.

Question files are validated before grading or saving. Each item must include
`id`, `question`, `must_contain_any`, `must_not_contain`,
`expect_top1_doc_id`, and `grading_criteria`. Duplicate IDs and malformed JSON
fail clearly. Expected document IDs outside the allowed/cleaned source set
produce a warning.

A failed custom question does not mean the official pipeline failed. It means
the current corpus, cleaning rules, index, or retrieval behavior does not yet
support that additional question as written.
