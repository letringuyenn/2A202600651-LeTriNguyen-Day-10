# Quality Report - Lab Day 10

**run_id:** `2026-06-10T09-08Z`  
**Ngày:** 10/06/2026  
**Manifest:** `artifacts/manifests/manifest_2026-06-10T09-08Z.json`

## 1. Tóm tắt số liệu

| Chỉ số | Trước cleaning | Sau cleaning | Diễn giải |
|---|---:|---:|---|
| Raw records | 247 | 247 đã đọc | Full fixture, không dùng smoke subset |
| Cleaned records | 0 chưa xử lý | 35 | Snapshot được publish |
| Quarantine records | 0 chưa phân loại | 160 | Có reason để điều tra |
| Duplicate candidates | 52 | 0 duplicate active chunk | Stable identity |
| Stale refund rows | 6 | 0 | 14 ngày không vào index |
| Stale HR rows | 27 | 0 | Bản 10 ngày không vào index |
| Non-ISO dates normalized | 10 | 0 non-ISO cleaned rows | Expectation PASS |
| Expectation halt | Chưa đánh giá | Không halt | `quality_status=PASS` |

Quarantine breakdown: 109 unknown source, 27 stale HR, 12 missing content,
6 missing effective date và 6 stale refund.

## 2. Before/after retrieval

Raw corruption cho refund chứa 6 dòng “14 ngày làm việc”. Sau cleaning:

| Slice | Before risk | After evidence |
|---|---|---|
| `q_refund_window` | Stale 14-day rows có thể được retrieve | top-1 `policy_refund_v4`; preview “7 ngày làm việc”; expected `yes`; forbidden `no` |
| `q_hr_annual_leave_under3` | 27 stale HR rows có giá trị 10 ngày/version cũ | top-1 `hr_leave_policy`; preview “12 ngày phép năm theo chính sách 2026”; expected `yes`; forbidden `no` |
| `gq_d10_10` | `access_control_sop` từng có nguy cơ bị allowlist loại | top-1 `access_control_sop`; expected content `true` |

Nguồn: `artifacts/eval/after_fix_eval.csv` và
`artifacts/eval/grading_run.jsonl`. CSV sau fix có 21/21 câu chứa expected term,
0/21 câu hit forbidden term. Official grading đạt 10/10.

Không có một CSV “before index” riêng trong repo; báo cáo không giả lập số liệu
retrieval trước fix. Before evidence được đo trực tiếp từ raw corruption counts,
còn after evidence lấy từ artifact eval được sinh bằng command.

## 3. Expectations

| Expectation | Severity | Kết quả |
|---|---|---|
| `min_one_row` | halt | PASS, 35 rows |
| `required_grading_sources_present` | halt | PASS, missing `[]` |
| `no_stale_refund_or_hr_content` | halt | PASS, stale rows `0` |
| `metadata_completeness` | halt | PASS, incomplete rows `0` |
| `effective_date_iso_yyyy_mm_dd` | halt | PASS, non-ISO rows `0` |
| `unique_chunk_id` | warn | PASS, duplicates `0` |

## 4. Freshness và monitor

SLA là 24 giờ tại publish. `latest_exported_at=2026-04-11T00:00:00`; kết quả
`freshness_hours=1449.136`, trạng thái FAIL. Diễn giải: dữ liệu mẫu cũ hơn SLA,
nhưng run ETL vẫn thành công. Không sửa timestamp giả để ép PASS.

## 5. Eval mở rộng

`artifacts/eval/custom_grading_run.jsonl` là slice 17 câu paraphrase/stress test.
Run hiện tại đạt 16/17. Ví dụ pass: stress refund/HR vẫn loại forbidden stale
terms. Ví dụ fail: `custom_d10_12` hỏi VPN bằng paraphrase xa, local hash
embedding xếp SLA lên trước. Kết quả này cho thấy official quality pass nhưng
retrieval semantic vẫn còn không gian cải tiến.

## 6. Hạn chế

- Chưa có GE/Pydantic runtime validation.
- Chưa đo freshness tại cả ingest và publish.
- HR version cutoff chưa đọc động từ contract.
- Local deterministic embedding phù hợp demo offline nhưng không phải semantic
  multilingual embedding production.
