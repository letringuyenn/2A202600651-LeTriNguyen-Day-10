# Báo cáo nhóm - Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** 2A202600651 - Lê Trí Nguyên

**Thành viên:** Lê Trí Nguyên

**Vai trò:** Ingestion, Cleaning & Quality, Embed & Idempotency, Monitoring,
Documentation và Web Demo

**Ngày nộp:** 10/06/2026

**Run chính:** `2026-06-10T09-08Z`

## 1. Pipeline tổng quan

Pipeline xử lý toàn bộ `data/raw/policy_export_dirty.csv`, không còn giới hạn ở
CI-smoke subset. Lệnh `etl_pipeline.py run` đọc 247 record, áp dụng cleaning và
quarantine, chạy expectation trước publish, ghi cleaned snapshot rồi upsert 35
chunk vào Chroma collection `day10_kb`. Mỗi run có `run_id` dùng xuyên suốt log,
manifest và metadata vector. Run tham chiếu nằm tại
`artifacts/logs/run_2026-06-10T09-08Z.log` và
`artifacts/manifests/manifest_2026-06-10T09-08Z.json`.

Kết quả: `raw_records=247`, `cleaned_records=35`,
`quarantine_records=160`, `quality_status=PASS`, publish `OK`,
`upserted_ids=35`. Pipeline exit 0 dù freshness FAIL, vì freshness phản ánh tuổi
snapshot chứ không phải lỗi transform/publish.

```powershell
.venv\Scripts\python.exe etl_pipeline.py run
```

## 2. Cleaning và expectations

Cleaning giữ đủ 5 nguồn grading, đặc biệt `access_control_sop`, đồng thời loại
unknown/legacy source, missing data, stale refund 14 ngày, stale HR 10 ngày,
chuẩn hóa ngày, loại duplicate và noise prefix. Critical expectations chạy ở
mức `halt`: required source coverage, stale-content absence, metadata
completeness và ISO effective date. `unique_chunk_id` là `warn`, vì duplicate
ID cần quan sát nhưng implementation hiện đã deduplicate trước publish.

### Metric impact

| Rule / expectation | Trước | Sau | Chứng cứ |
|---|---:|---:|---|
| Source allowlist | 109 unknown rows trong raw | 109 quarantined; đủ 5 grading sources | manifest `cleaning_stats`; `missing_doc_ids=[]` |
| Missing content/date | 18 invalid rows | 18 quarantined | log `09-08Z` |
| Stale refund | 6 rows chứa 14 ngày | 0 stale row trong cleaned | `stale_refund_rows_removed=6`; expectation PASS |
| HR version conflict | 27 stale HR rows | 0 stale row; HR 2026 còn lại | `stale_hr_rows_removed=27`; `gq_d10_09` PASS |
| Date normalization | 10 non-ISO dates có thể sửa | 10 normalized; `non_iso_rows=0` | manifest + expectation |
| Duplicate handling | 52 duplicate rows | 52 removed; 35 stable chunks | `duplicate_rows_removed=52` |
| Noise stripping | 9 noisy prefixes | 9 stripped | `noise_prefixes_stripped=9` |
| Metadata completeness | Nguy cơ thiếu metadata | `incomplete_rows=0` | quality summary |

Ví dụ negative-path: expectation được thiết kế để halt trước embed nếu thiếu
grading source hoặc stale content còn tồn tại. Run nộp bài không dùng
`--skip-validate`; log xác nhận toàn bộ halt expectations PASS.

## 3. Before/after retrieval và eval mở rộng

Raw fixture là corruption inject: có 6 refund rows 14 ngày, 27 HR rows stale,
52 duplicate, 18 thiếu content/date và 109 source không hợp lệ. Sau cleaning,
`q_refund_window` trả top-1 `policy_refund_v4`, preview “7 ngày làm việc”,
`contains_expected=yes`, `hits_forbidden=no`. Slice HR
`q_hr_annual_leave_under3` trả `hr_leave_policy`, “12 ngày phép năm”,
`contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`.

`artifacts/eval/after_fix_eval.csv` có 21 dòng; tất cả 21 dòng
`contains_expected=yes` và `hits_forbidden=no`. Official
`artifacts/eval/grading_run.jsonl` có đúng 10 dòng và đạt 10/10, bao gồm hai câu
khó `gq_d10_09` và `gq_d10_10`.

Bằng chứng vượt baseline là `artifacts/eval/custom_grading_run.jsonl`: 17 câu
paraphrase/stress-test, chạy cùng phương pháp top-k + keyword + expected source.
Kết quả hiện tại 16/17 pass. Failure được giữ trung thực: `custom_d10_12` là
paraphrase VPN có expected source trong top-k nhưng không top-1, cho thấy local
hash embedding thiên lexical. Đây là ví dụ fail/pass và định hướng cải tiến
semantic/hybrid retrieval, không sửa pipeline chỉ để làm đẹp điểm custom.

## 4. Freshness và monitoring

Contract chọn SLA 24 giờ tại boundary publish, dựa trên
`latest_exported_at`. Run `09-08Z` có timestamp dữ liệu mới nhất
`2026-04-11T00:00:00`, nên tại ngày 10/06/2026 freshness là khoảng
`1449.136` giờ và trạng thái FAIL. Đây là kết quả đúng: sample snapshot đã cũ.
UI giải thích đây là observability warning, trong khi quality vẫn PASS và
pipeline vẫn exit 0. Manifest cũng cung cấp `last_successful_run_id`,
`cleaned_records` và `quarantine_records` để điều tra.

## 5. Idempotency và liên hệ Day 9

Run `09-04Z` và `09-08Z` đều upsert đúng 35 stable IDs; manifest mới nhất có
`pruned_ids=0`, chứng minh rerun không tăng collection và không còn stale ID.
Day 9 integration được chủ động hoãn. Day 10 dùng collection riêng `day10_kb`
và metadata đủ cho adapter sau này, nhưng không sửa supervisor, trace format,
`web_demo.py` hoặc HTML của Day 9.

## 6. Rủi ro còn lại

- HR cutoff vẫn hard-code thay vì đọc trực tiếp từ contract/env.
- Freshness mới đo một boundary, chưa đủ bonus hai boundary.
- Deterministic hash embedding yếu với paraphrase xa.
- Chưa có Great Expectations/Pydantic runtime model; không nhận bonus mục này.
- Đây là lab cục bộ, chưa có scheduler và alert production.
