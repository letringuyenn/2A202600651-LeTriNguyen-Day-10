# Kiến trúc pipeline - Lab Day 10

**Nhóm:** 2A202600651 - Lê Trí Nguyên

**Cập nhật:** 10/06/2026

**Run tham chiếu:** `2026-06-10T09-08Z`

## 1. Sơ đồ luồng

```text
data/raw/policy_export_dirty.csv
              |
              v
     Ingest: load_raw_csv()
     - gắn run_id
     - đếm raw_records
              |
              v
 transform/cleaning_rules.py ----------------> artifacts/quarantine/
 - source allowlist                           quarantine_<run_id>.csv
 - missing content/date
 - stale refund / stale HR
 - normalize date / noise
 - deduplicate + stable chunk_id
              |
              v
 quality/expectations.py
 - halt: source coverage, stale absence,
         metadata completeness, ISO date
 - warn: unique chunk_id
              |
              v
 artifacts/cleaned/cleaned_<run_id>.csv
              |
              v
 Chroma collection: day10_kb
 - upsert stable chunk_id
 - prune stale vector IDs
 - attach source/run metadata
              |
              +--------------------+
              |                    |
              v                    v
 eval_retrieval.py          grading_run.py
 CSV evidence               official/custom JSONL
              |
              v
 monitoring/freshness_check.py
 - boundary hiện tại: latest exported_at tại publish
 - SLA: 24 giờ
              |
              v
 artifacts/manifests/manifest_<run_id>.json
 day10_web_demo.py (quan sát và chạy demo)
```

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner |
|---|---|---|---|
| Ingest | `data/raw/policy_export_dirty.csv` | Danh sách 247 raw rows | Lê Trí Nguyên |
| Transform | Raw rows | 35 cleaned candidates + 160 quarantine rows | Lê Trí Nguyên |
| Quality | Cleaned candidates | PASS/FAIL theo expectation, halt trước publish | Lê Trí Nguyên |
| Embed | Cleaned CSV | Chroma `day10_kb`, 35 vector IDs | Lê Trí Nguyên |
| Eval | Chroma + question JSON | CSV/JSONL retrieval evidence | Lê Trí Nguyên |
| Monitor | Manifest + `latest_exported_at` | Freshness PASS/FAIL và số giờ | Lê Trí Nguyên |
| Demo | Manifest/artifact/CLI | FastAPI + HTML/CSS/JS UI | Lê Trí Nguyên |

Ranh giới quan trọng là expectation chạy trước embed. Nếu một expectation mức
`halt` thất bại, pipeline dừng và không publish snapshot lỗi. Quarantine là đầu
ra có thể điều tra, không phải xóa âm thầm.

## 3. Idempotency và rerun

`chunk_id` được tạo ổn định từ `doc_id`, `effective_date` và hash nội dung đã
chuẩn hóa. Publish dùng `collection.upsert()` theo ID này. Trước upsert, pipeline
đọc các ID đang tồn tại và xóa tập `existing_ids - current_snapshot_ids`.

Hai run `2026-06-10T09-04Z` và `2026-06-10T09-08Z` đều ghi:

```text
cleaned_records=35
embed_upsert count=35 collection=day10_kb
```

Manifest `09-08Z` ghi `upserted_ids=35`, `pruned_ids=0`, `row_count=35`. Việc
rerun không làm collection phình thêm; `pruned_ids=0` cho biết không có vector
lạc hậu trong lần chạy này.

## 4. Liên hệ Day 8/9

Day 8 và Day 9 không bị sửa. Day 10 publish sang collection riêng `day10_kb`
để kiểm chứng data pipeline độc lập. Metadata gồm `chunk_id`, `doc_id`,
`source_name`, `source_system`, `source_domain`, `effective_date`,
`exported_at`, `run_id` và `retriever`, đủ cho adapter retrieval ở giai đoạn
sau. Việc nối worker Day 9 vào collection này được chủ động hoãn để tránh thay
đổi supervisor, trace format và demo đang ổn định.

## 5. Rủi ro đã biết

- Freshness đang FAIL vì dữ liệu mẫu mới nhất là `2026-04-11`, cũ hơn SLA 24 giờ.
- Local hash embedding thiên về lexical overlap, chưa mạnh với paraphrase xa.
- Freshness mới đo một boundary publish, chưa đủ điều kiện bonus hai boundary.
- Pipeline là lab cục bộ, chưa có scheduler, alert channel hoặc rollback production.
