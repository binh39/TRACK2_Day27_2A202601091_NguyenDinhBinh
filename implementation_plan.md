# Kế hoạch thực hiện Lab 27 — Data Reliability Game Day

## Tổng quan
Mục tiêu của bài lab là xây dựng hệ thống toàn diện cho **Data Observability, Data Contracts, dbt Testing, Anomaly Detection, Lineage, SLO và Incident Response**, đảm bảo pipeline dữ liệu e-commerce và AI Support Agent hoạt động tin cậy, phát hiện và cô lập sự cố trước khi ảnh hưởng đến người dùng cuối.

Tất cả các API giao tiếp cần tuân thủ giao diện chuẩn trong [docs/STUDENT_API.md](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/docs/STUDENT_API.md) và vượt qua toàn bộ public test suite cũng như 20 hidden evaluation test cases.

---

## Các giai đoạn thực hiện (Phases)

### Giai đoạn 0: Thiết lập Môi trường & Baseline
1. Tạo môi trường ảo Python `venv` (`.venv`).
2. Cài đặt các thư viện từ [requirements.txt](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/requirements.txt).
3. Kiểm tra `.gitignore` để đảm bảo không ignore các file nộp bài (`reports/`, `contracts/`, `src/`, `observability/`, `gx/`, `dbt_project/`, `dashboard/`).
4. Chạy `make reset` và `make baseline` để khởi tạo dữ liệu chuẩn ban đầu.

---

### Giai đoạn 1: Data Contracts & Validation (`src/` & `contracts/` & `gx/`)
- **[MODIFY] [src/contract_validator.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/src/contract_validator.py)**:
  - Hỗ trợ cả định dạng schema `columns` và `fields` (như trong [contracts/kb_contract.yaml](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/contracts/kb_contract.yaml)).
  - Bổ sung **Type Validation** cho các kiểu: `integer`, `string`, `number`/`float`, `datetime`, `boolean`.
  - Bổ sung **Freshness Validation** đối chiếu `updated_at`/`published_at` với ngưỡng `max_delay_minutes`.
  - Bổ sung kiểm tra **`min_length`** cho văn bản.
  - Phân loại **Severity** (`critical`, `warning`, `info`) và định nghĩa hàm xử lý **Action** (`block`, `quarantine`, `warn`).
- **[MODIFY] [gx/validate_orders.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/gx/validate_orders.py)**:
  - Đóng gói các kỳ vọng kiểm tra thành Great Expectations 1.21 `ExpectationSuite` + `ValidationDefinition` + `Checkpoint` + Action summary.
- **Git Commit 1**: `feat(contracts): add type checking, freshness, severity actions, and GX checkpoint`

---

### Giai đoạn 2: dbt Transformation Protection & Testing (`dbt_project/`)
- **[MODIFY] [dbt_project/models/marts/fct_daily_revenue.sql](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dbt_project/models/marts/fct_daily_revenue.sql)**:
  - Đảm bảo logic join với `stg_customers` không làm nhân bản số dòng khi có nhiều bản ghi active (SCD duplication protection).
- **[MODIFY] [dbt_project/models/staging/schema.yml](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dbt_project/models/staging/schema.yml)** & **[dbt_project/models/marts/schema.yml](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dbt_project/models/marts/schema.yml)**:
  - Bổ sung generic data tests (not_null, unique, accepted_values, relationships).
- **[NEW] [dbt_project/models/marts/unit_tests.yml](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dbt_project/models/marts/unit_tests.yml)**:
  - Viết dbt unit test kiểm thử trường hợp chuẩn và trường hợp customer dimension có nhiều bản ghi để chống lạm phát doanh thu.
- **[NEW] [dbt_project/tests/assert_daily_revenue_matches_completed_orders.sql](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dbt_project/tests/assert_daily_revenue_matches_completed_orders.sql)**:
  - Viết singular business test so sánh tổng doanh thu ngày trong `fct_daily_revenue` với tổng số tiền các đơn hàng `completed` trong `stg_orders`.
- **Git Commit 2**: `feat(dbt): enhance marts join safety, add generic/singular tests and dbt unit tests`

---

### Giai đoạn 3: Anomaly Detection & Distribution Drift (`observability/`)
- **[MODIFY] [observability/anomaly.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/observability/anomaly.py)**:
  - Xử lý triệt để biên `mad == 0` trong `mad_detector`.
  - Nâng cấp `method="auto"` trở nên thông minh (context-aware): hỗ trợ `day_of_week` (seasonality), `same_segment_history`, lọc outliers, kết hợp MAD và Z-score.
- **[MODIFY] [observability/distribution.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/observability/distribution.py)**:
  - Nâng cấp kiểm định phân phối kết hợp tỉ lệ trung bình, median shift, IQR và chuẩn hóa dữ liệu phát hiện distribution drift.
- **Git Commit 3**: `feat(observability): upgrade auto anomaly detector and distribution drift detection`

---

### Giai đoạn 4: Lineage & Transitive Traversal (`observability/lineage.py`)
- **[MODIFY] [observability/lineage.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/observability/lineage.py)**:
  - Cài đặt thuật toán BFS đệ quy/transitive đầy đủ cho `get_column_downstream(column_graph, start_column)`.
  - Bổ sung trích xuất dbt manifest lineage đa tầng.
- **Git Commit 4**: `feat(lineage): implement transitive column lineage traversal and manifest parsing`

---

### Giai đoạn 5: SLO Multi-window Burn Rate & RAG Metrics (`observability/`)
- **[MODIFY] [observability/slo.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/observability/slo.py)**:
  - Cài đặt chính sách `evaluate_multiwindow_burn`: phân biệt transient spike ngắn (không page, severity warning) và sustained fast burn kéo dài (page = True, severity critical) dựa theo chuẩn Google SRE Workbook.
- **[MODIFY] [observability/rag_metrics.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/observability/rag_metrics.py)**:
  - Hoàn thiện `detect_embedding_norm_shift` phát hiện độ lệch không gian vector/độ dài chuẩn hóa (embedding drift).
- **Git Commit 5**: `feat(slo-rag): implement multi-window burn rate policy and embedding drift detection`

---

### Giai đoạn 6: Kiểm thử 3 Fault Scenarios & Cải tiến Dashboard
- Chạy thử nghiệm và xác nhận 3 kịch bản lỗi:
  1. `duplicate_pk`: phát hiện duplicate khóa chính qua contracts & dbt tests.
  2. `volume_drop`: phát hiện sụt giảm dung lượng qua auto anomaly detector.
  3. `stale_kb`: phát hiện tài liệu KB quá hạn qua freshness check và SLO.
- **[MODIFY] [dashboard/app.py](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/dashboard/app.py)**:
  - Hiển thị đầy đủ SLO targets, remaining budget, burn-rate windows, lineage graph và trạng thái incident trực quan.
- **Git Commit 6**: `feat(dashboard): enrich streamlit observability dashboard and verify fault scenarios`

---

### Giai đoạn 7: Báo cáo & Tài liệu (Tiếng Việt)
- **[MODIFY] [reports/incident_report.md](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/reports/incident_report.md)**:
  - Viết báo cáo sự cố toàn diện bằng tiếng Việt: Mức độ nghiêm trọng, Tóm tắt sự cố, Dấu hiệu phát hiện, Nguyên nhân gốc rễ (Root Cause), Bằng chứng (Evidence), Phạm vi ảnh hưởng (Blast Radius), Biện pháp khắc phục (Mitigation), Phục hồi (Recovery) và Hành động phòng ngừa (Prevention / Action Items).
- **[MODIFY] [reports/agent_log.md](file:///d:/VinAI/Labs/TRACK2_Day27_2A202601091_NguyenDinhBinh/reports/agent_log.md)**:
  - Ghi lại các quyết định thiết kế kiến trúc và tương tác AI Agent bằng tiếng Việt theo mẫu.
- **Git Commit 7 & Push**: `docs(reports): complete incident report and agent decision log in vietnamese` -> `git push origin main`.

---

## Kế hoạch Kiểm tra & Xác minh (Verification Plan)

### Automated Tests
- Chạy toàn bộ test suite công khai:
  ```powershell
  .venv\Scripts\pytest tests_public -v
  ```
- Chạy kiểm tra Great Expectations:
  ```powershell
  .venv\Scripts\python gx\validate_orders.py
  ```
- Đồng bộ hạt giống và chạy kiểm tra dbt (models, singular tests, unit tests):
  ```powershell
  .venv\Scripts\python scripts\sync_dbt_seeds.py
  .venv\Scripts\dbt build --project-dir dbt_project --profiles-dir dbt_project
  ```
- Chạy kịch bản baseline chuẩn:
  ```powershell
  .venv\Scripts\python scripts\run_baseline.py
  ```

### Fault Scenario Validation
- Kiểm tra lần lượt 3 kịch bản lỗi:
  ```powershell
  .venv\Scripts\python scripts\inject_fault.py duplicate_pk
  .venv\Scripts\python scripts\run_baseline.py
  .venv\Scripts\python scripts\reset_lab.py

  .venv\Scripts\python scripts\inject_fault.py volume_drop
  .venv\Scripts\python scripts\run_baseline.py
  .venv\Scripts\python scripts\reset_lab.py

  .venv\Scripts\python scripts\inject_fault.py stale_kb
  .venv\Scripts\python scripts\run_baseline.py
  .venv\Scripts\python scripts\reset_lab.py
  ```
