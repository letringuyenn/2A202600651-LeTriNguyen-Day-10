# Data contract - Lab Day 10

Nguồn cấu hình máy đọc: `contracts/data_contract.yaml`, version `1.1`.

## 1. Source map

| `doc_id` | Nguồn logic | Domain | Owner | Failure mode chính | Metric/check |
|---|---|---|---|---|---|
| `policy_refund_v4` | CS refund policy | CS Helpdesk | CS Operations | stale 14 ngày, duplicate | `stale_refund_rows_removed`, forbidden-content expectation |
| `sla_p1_2026` | P1 SLA | IT Operations | IT Operations | thiếu ngày, duplicate | ISO date, source coverage |
| `it_helpdesk_faq` | Helpdesk FAQ | IT Helpdesk | IT Helpdesk | missing/noisy content | metadata completeness |
| `hr_leave_policy` | HR leave 2026 | HR | HR Operations | conflict 10/12 ngày | `stale_hr_rows_removed`, stale absence |
| `access_control_sop` | Access control SOP | IT Security | IT Security | bị allowlist loại nhầm | required source coverage |

Raw input được ingest bằng CSV từ `data/raw/policy_export_dirty.csv`. Các
`invalid_doc_*`, `legacy_*` và source ngoài danh sách canonical không được đưa
vào cleaned snapshot.

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|---|---|---:|---|
| `chunk_id` | string | Có | ID ổn định từ source, effective date và content hash |
| `doc_id` | string | Có | Một trong 5 canonical source IDs |
| `chunk_text` | string | Có | Nội dung đã loại noise; tối thiểu có ý nghĩa |
| `effective_date` | ISO date | Có | Chuẩn `YYYY-MM-DD` |
| `exported_at` | datetime | Có | Dùng đo freshness snapshot |
| `title` | string | Có | Tên tài liệu |
| `source_name` | string | Có | Nhãn nguồn cho retrieval/citation |
| `source_system` | string | Có | Hệ thống nguồn |
| `source_domain` | string | Có | Domain CS/IT/HR/security |
| `source_path` | string | Không | Đường dẫn nguồn nếu export cung cấp |
| `cleaning_flags` | JSON string | Không | Các biến đổi nội dung đã áp dụng |

Metadata publish bổ sung `run_id` và `retriever=day10_etl`.

## 3. Quarantine và drop

Record bị loại được ghi vào
`artifacts/quarantine/quarantine_<run_id>.csv` cùng trường `reason`; pipeline
không xóa âm thầm. Run `2026-06-10T09-08Z` có:

| Reason | Count |
|---|---:|
| `unknown_doc_id` | 109 |
| `stale_hr_policy_effective_date` | 27 |
| `missing_chunk_text` | 12 |
| `missing_effective_date` | 6 |
| `stale_refund_window` | 6 |

Owner nguồn phải sửa dữ liệu upstream hoặc cập nhật contract có review trước
khi record được merge lại. Không sửa trực tiếp quarantine artifact.

## 4. Phiên bản và canonical

- Refund canonical: `policy_refund_v4`, thời hạn hiện hành 7 ngày làm việc.
- HR canonical: `hr_leave_policy` từ `2026-01-01`; giá trị dưới 3 năm là 12 ngày.
- Access canonical: `access_control_sop`; Level 4 cần IT Manager/CISO.
- Freshness SLA: 24 giờ, đo từ `latest_exported_at` tại publish.

Các rule version hiện bám `policy_versioning` trong YAML về mặt tài liệu, nhưng
cutoff HR trong implementation vẫn còn hard-code. Đây là hạng mục cải tiến,
không được khai là rule versioning động.
