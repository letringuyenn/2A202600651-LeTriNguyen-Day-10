# Báo cáo cá nhân - Lab Day 10

**Họ và tên:** Lê Trí Nguyên  
**Mã:** 2A202600651  
**Vai trò:** Ingestion, Cleaning, Quality, Embed, Monitoring và Demo  
**Ngày nộp:** 10/06/2026  
**Run chính:** `2026-06-10T09-08Z`

## 1. Phần tôi phụ trách

Tôi phụ trách toàn bộ luồng Day 10 từ raw data đến artifact quan sát được. Các
file chính tôi làm gồm `transform/cleaning_rules.py`,
`quality/expectations.py`, `etl_pipeline.py`,
`monitoring/freshness_check.py`, `contracts/data_contract.yaml`,
`retrieval_embedding.py`, `eval_retrieval.py` và `grading_run.py`. Tôi cũng làm
lớp demo `day10_web_demo.py` cùng HTML/CSS/JS để chạy pipeline, eval, grading và
xem freshness. Tôi giữ Day 8 và Day 9 không thay đổi, dùng collection riêng
`day10_kb`, rồi chuẩn bị metadata để tích hợp sau. Bằng chứng thực tế là log
`artifacts/logs/run_2026-06-10T09-08Z.log`, manifest cùng run ID và các artifact
eval. Repo hiện không có commit ownership riêng cho từng thành viên, vì vậy tôi
không khai commit không tồn tại.

## 2. Một quyết định kỹ thuật

Quyết định quan trọng nhất của tôi là phân biệt expectation `halt` và `warn`.
Các lỗi có thể làm RAG trả lời sai chính sách như thiếu source grading, stale
refund/HR, thiếu metadata hoặc effective date không chuẩn ISO đều ở mức
`halt`. Chúng phải dừng pipeline trước Chroma publish. `unique_chunk_id` được
đặt `warn`, vì duplicate đã được xử lý trong transform nhưng vẫn cần metric để
quan sát. Run nộp bài không dùng `--skip-validate`; manifest ghi
`quality_halt=false`. Với freshness, tôi không ép dữ liệu mẫu thành PASS:
snapshot mới nhất là ngày 11/04/2026 nên freshness FAIL ở SLA 24 giờ là đúng,
trong khi quality và publish vẫn PASS. Cách tách này tránh biến một cảnh báo vận
hành thành lỗi dữ liệu giả.

## 3. Một anomaly đã xử lý

Anomaly lớn nhất là conflict phiên bản. Raw CSV chứa refund 14 ngày và HR 10
ngày, trong khi policy hiện hành là refund 7 ngày và HR 2026 có 12 ngày cho nhân
viên dưới ba năm. Nếu chỉ embed toàn bộ CSV, retrieval có thể chọn bản cũ dù
model không sai. Tôi thêm rule nhận diện stale content/version, quarantine thay
vì sửa artifact bằng tay, và thêm expectation
`no_stale_refund_or_hr_content`. Run `09-08Z` đo được
`stale_refund_rows_removed=6`, `stale_hr_rows_removed=27`; expectation sau clean
ghi `stale_rows=0`. Đồng thời `access_control_sop` được giữ trong allowlist,
giúp câu Level 4 Admin Access lấy đúng source. Đây là sửa ở data layer thay vì
prompt engineering.

## 4. Bằng chứng trước và sau

Trước cleaning, fixture có 247 dòng gồm 109 unknown source, 18 dòng thiếu
content/date, 52 duplicate, 6 stale refund và 27 stale HR. Sau pipeline còn 35
cleaned records, 160 quarantine records, quality PASS và Chroma có 35 stable
IDs. Trong `artifacts/eval/after_fix_eval.csv`, `q_refund_window` trả
`policy_refund_v4`, chứa “7 ngày làm việc”, `hits_forbidden=no`;
`q_hr_annual_leave_under3` trả `hr_leave_policy`, chứa “12 ngày phép năm” và
không chứa giá trị stale. `artifacts/eval/grading_run.jsonl` đạt đủ 10/10,
bao gồm `gq_d10_09` và `gq_d10_10`. Hai rerun `09-04Z` và `09-08Z` đều upsert
35 IDs, nên index không phình.

## 5. Cải tiến nếu có thêm hai giờ

Tôi sẽ thay local hash embedding bằng multilingual semantic embedding hoặc
hybrid BM25-vector retrieval, sau đó rerun slice custom 17 câu. Hiện custom đạt
16/17; một câu VPN paraphrase xa bị SLA vượt top-1. Tôi cũng sẽ đọc HR cutoff
trực tiếp từ `data_contract.yaml` thay vì hard-code, rồi thêm test inject chứng
minh thay đổi contract làm thay đổi quyết định quarantine.
