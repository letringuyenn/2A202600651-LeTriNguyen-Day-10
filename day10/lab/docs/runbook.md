# Runbook - Lab Day 10

## Symptom

Người dùng hoặc agent trả lời policy cũ, ví dụ refund 14 ngày thay vì 7 ngày,
HR dưới 3 năm có 10 ngày thay vì 12 ngày; top-1 đến sai `doc_id`; pipeline exit
khác 0; hoặc UI hiển thị freshness FAIL.

## Detection

1. Mở manifest mới nhất và kiểm tra `quality_status`, `quality_summary`,
   `cleaning_stats` và `publish`.
2. Tìm `expectation[...] FAIL` hoặc `PIPELINE_HALT` trong log cùng `run_id`.
3. Kiểm tra `hits_forbidden`, `contains_expected`, `top1_doc_matches` trong
   `artifacts/eval/grading_run.jsonl`.
4. Với dữ liệu cũ, đọc `freshness_hours` và `freshness_sla_hours`; không đánh
   đồng freshness FAIL với quality failure.

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|---|---|---|
| 1 | Chạy `python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl` | Xác nhận đủ 10 câu và format hợp lệ |
| 2 | Mở `artifacts/manifests/manifest_<run_id>.json` | Các count khớp log, quality PASS |
| 3 | Mở `artifacts/quarantine/quarantine_<run_id>.csv` | Có reason cụ thể cho record bị loại |
| 4 | Chạy `python eval_retrieval.py --out artifacts/eval/diagnostic.csv` | Xác định top-1/source/forbidden term |
| 5 | Kiểm tra collection count và log `embed_prune_removed` | Count bằng cleaned snapshot, không có stale IDs |

Nếu custom grading fail nhưng official grading pass, kiểm tra trước tiên
`expect_top1_doc_id` của câu custom và mức lexical overlap. Đây có thể là lỗi
câu hỏi hoặc hạn chế embedding, không phải lỗi ETL.

## Mitigation

- Nếu expectation halt: không dùng `--skip-validate` cho run nộp bài; sửa rule
  hoặc source contract, sau đó rerun toàn pipeline.
- Nếu stale policy lọt qua: quarantine source/version lỗi và regenerate artifact.
- Nếu collection lệch snapshot: rerun publish; stable IDs sẽ upsert và stale IDs
  được prune.
- Nếu chỉ freshness FAIL do fixture cũ: giữ cảnh báo trên UI và ghi rõ đây là
  observability signal; không sửa timestamp giả để đổi kết quả.
- Nếu custom query paraphrase fail: giữ official pipeline, phân tích top-k trước
  khi quyết định đổi embedding/hybrid retrieval.

## Recovery

Chạy theo thứ tự:

```powershell
.venv\Scripts\python.exe etl_pipeline.py run
.venv\Scripts\python.exe eval_retrieval.py --out artifacts/eval/after_fix_eval.csv
.venv\Scripts\python.exe grading_run.py --out artifacts/eval/grading_run.jsonl
.venv\Scripts\python.exe -X utf8 instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
```

Chỉ coi recovery thành công khi pipeline exit 0, manifest PASS, collection count
bằng `cleaned_records`, và official grading 10/10.

## Prevention

- Duy trì source allowlist và owner trong data contract.
- Bắt buộc source coverage, stale absence, metadata completeness và ISO date ở
  mức halt.
- Theo dõi metric impact mỗi run thay vì chỉ kiểm tra code tồn tại.
- Chạy official grading trong CI trước khi publish artifact.
- Tương lai: đọc cutoff/version từ contract, thêm semantic/hybrid retrieval,
  đo freshness ở ingest và publish, và cấu hình alert channel thật.
