# Nhật ký Quyết định AI Agent (AI Agent Decision Log)

## Quyết định 1: Thiết kế Type Validation & Freshness trong Contract Validator
- **Giả thuyết (Hypothesis)**: Pipeline có thể vượt qua các kiểm tra not_null cơ bản nhưng vẫn bị lỗi nếu kiểu dữ liệu bị biến đổi (type drift) hoặc dữ liệu bị chậm cập nhật (stale data).
- **Yêu cầu đối với Agent (Prompt / Request to agent)**: Bổ sung type checking, freshness validation, `min_length`, phân loại mức độ nghiêm trọng (severity) và hành động (action: block/warn/allow) vào `src/contract_validator.py`.
- **Đề xuất của Agent (Agent proposal)**: 
  1. Hỗ trợ cả hai cấu trúc `columns` và `fields` trong file YAML.
  2. Kiểm tra chặt chẽ kiểu dữ liệu `integer`, `float`, `datetime`, `boolean`, `string`.
  3. Tính toán độ trễ thời gian thực so với cấu hình `freshness` và phân loại hành động tự động.
- **Bằng chứng / Kiểm thử (Evidence/Test)**: `pytest tests_public/test_contracts.py` đạt 100%, phát hiện thành công type drift trên cột `amount` và độ trễ quá hạn trên `updated_at`.
- **Quyết định (Accept / Reject / Revise)**: **Accept**.
- **Lý do (Why)**: Đảm bảo dữ liệu được kiểm soát chất lượng từ cổng vào, ngăn chặn lỗi lan truyền xuống tầng hạ nguồn.

---

## Quyết định 2: Bảo vệ Mô hình dbt Marts chống Lạm phát Doanh thu do SCD Duplication
- **Giả thuyết (Hypothesis)**: Bảng khách hàng `stg_customers` có thể có nhiều dòng `is_active = true` cho cùng một khách hàng. Khi `left join`, số dòng đơn hàng sẽ bị nhân bản, làm sai lệch doanh thu trên báo cáo CEO.
- **Yêu cầu đối với Agent (Prompt / Request to agent)**: Viết dbt unit test để chứng minh lỗi này và tái cấu trúc model `fct_daily_revenue.sql` để an toàn trước dữ liệu SCD trùng lặp.
- **Đề xuất của Agent (Agent proposal)**:
  1. Thêm subquery deduplication sử dụng hàm cửa sổ `row_number() over (partition by customer_id order by valid_from desc) = 1`.
  2. Tạo singular test `assert_daily_revenue_matches_completed_orders.sql` so khớp doanh thu ngày với `stg_orders`.
  3. Tạo `unit_tests.yml` kiểm thử cả trường hợp chuẩn và trường hợp customer dimension có nhiều bản ghi active.
- **Bằng chứng / Kiểm thử (Evidence/Test)**: `dbt build` vượt qua 19/19 checks, bao gồm 2 unit tests và 1 singular test.
- **Quyết định (Accept / Reject / Revise)**: **Accept**.
- **Lý do (Why)**: Đảm bảo tính toán tài chính chính xác tuyệt đối ngay cả khi dữ liệu kích thước khách hàng bị bất thường.

---

## Quyết định 3: Triển khai Cảnh báo Multi-Window Multi-Burn-Rate theo chuẩn Google SRE
- **Giả thuyết (Hypothesis)**: Cảnh báo lỗi đơn cửa sổ (single window) dễ gây báo động giả khi có đột biến tạm thời (transient spike) hoặc không đủ nhạy để phát hiện lỗi chậm (slow burn).
- **Yêu cầu đối với Agent (Prompt / Request to agent)**: Xây dựng hàm `evaluate_multiwindow_burn` kết hợp cửa sổ ngắn và cửa sổ dài để quyết định gửi cảnh báo khẩn cấp (`page=True`).
- **Đề xuất của Agent (Agent proposal)**:
  - Chỉ gửi trang (`page=True, severity="critical"`) khi CẢ cửa sổ ngắn và dài đều vượt ngưỡng burn rate (>= 14.4x).
  - Đưa ra mức cảnh báo (`severity="warning"`) khi chỉ có đột biến tạm thời hoặc cháy ngân sách chậm.
- **Bằng chứng / Kiểm thử (Evidence/Test)**: `pytest tests_public/test_slo.py` xác minh đúng hành vi phân biệt transient spike và sustained fast burn.
- **Quyết định (Accept / Reject / Revise)**: **Accept**.
- **Lý do (Why)**: Giảm thiểu mệt mỏi cảnh báo (alert fatigue) cho đội ngũ trực vận hành On-call.

---

## Quyết định 4: Duyệt Đồ thị Phụ thuộc Transitive BFS cho Column Lineage
- **Giả thuyết (Hypothesis)**: Truy vết ảnh hưởng (Blast Radius) cấp độ cột đòi hỏi phải đi qua toàn bộ các mắt xích trung gian từ bảng nguồn đến dashboard.
- **Yêu cầu đối với Agent (Prompt / Request to agent)**: Hoàn thiện `get_column_downstream` để trả về danh sách các cột chịu ảnh hưởng trực tiếp và gián tiếp.
- **Đề xuất của Agent (Agent proposal)**: Cài đặt thuật toán duyệt Breadth-First Search (BFS) sử dụng hàng đợi `collections.deque` và tập `seen` chống lặp vô hạn.
- **Bằng chứng / Kiểm thử (Evidence/Test)**: `pytest tests_public/test_lineage.py` vượt qua toàn bộ ca kiểm thử chuỗi phụ thuộc `raw_orders.amount -> stg_orders.amount_usd -> fct_daily_revenue.daily_revenue -> ceo_revenue_dashboard.revenue`.
- **Quyết định (Accept / Reject / Revise)**: **Accept**.
- **Lý do (Why)**: Cung cấp bức tranh phạm vi ảnh hưởng chính xác giúp kỹ sư ước lượng rủi ro sự cố tức thì.

---

## Quyết định 5: Tự động Phân tách và Cô lập Dữ liệu Lỗi (Automatic Quarantine)
- **Giả thuyết (Hypothesis)**: Khi batch dữ liệu chứa cả bản ghi hợp lệ và bản ghi hỏng, việc block toàn bộ file sẽ gây gián đoạn kinh doanh không cần thiết.
- **Yêu cầu đối với Agent**: Xây dựng module `src/quarantine.py` tự động lọc dòng hợp lệ đưa vào pipeline và cô lập dòng lỗi vào thư mục riêng với metadata lý do.
- **Đề xuất của Agent**: Cài đặt hàm `quarantine_records` trả về `(clean_df, quarantined_df, summary)` và lưu vào `data/quarantine/orders_quarantined.csv`.
- **Bằng chứng / Kiểm thử**: `test_bonus_4_automatic_quarantine` xác minh phân tách chính xác dòng trùng khóa, âm tiền, sai enum.
- **Quyết định**: **Accept**.
- **Lý do**: Tối ưu hóa tính khả dụng (High Availability) mà vẫn đảm bảo độ tin cậy dữ liệu.

---

## Quyết định 6: Tích hợp Chuẩn Soda Core Data Contract Adapter
- **Giả thuyết (Hypothesis)**: Doanh nghiệp có thể sử dụng cú pháp Soda Core để khai báo Data Contract giữa các team sản xuất và tiêu thụ dữ liệu.
- **Yêu cầu đối với Agent**: Thiết lập `contracts/soda_orders_contract.yml` và engine `src/soda_validator.py`.
- **Đề xuất của Agent**: Hỗ trợ đầy đủ các checks `missing_count`, `duplicate_count`, `min`, `invalid_count(valid_values)`, `freshness`, `row_count`.
- **Bằng chứng / Kiểm thử**: `test_bonus_5_soda_data_contract` vượt qua 17 checks chuẩn Soda Core.
- **Quyết định**: **Accept**.

---

## Quyết định 7: Tích hợp Chuẩn OpenLineage & Elementary OSS Data Observability
- **Giả thuyết (Hypothesis)**: Tích hợp các chuẩn mở ngành (OpenLineage 1.x và Elementary OSS) giúp tương thích với Marquez, DataHub và hệ sinh thái Modern Data Stack.
- **Yêu cầu đối với Agent**: Phát triển `observability/openlineage_emitter.py` và `src/elementary_reporter.py`.
- **Đề xuất của Agent**: Xuất các RunEvent OpenLineage chuẩn kèm Column Lineage Facet và xuất báo cáo `reports/elementary_report.json` theo dõi table/column anomalies và dbt test runs.
- **Bằng chứng / Kiểm thử**: `test_bonus_6_elementary_oss_reporting` và `test_bonus_7_openlineage_events` đạt 100%.
- **Quyết định**: **Accept**.

---

## Quyết định 8: Giám sát Semantic Cosine Drift & Token Distribution cho AI/RAG
- **Giả thuyết (Hypothesis)**: AI Support Agent có thể bị suy giảm chất lượng nếu tri thức RAG bị trôi dạt ngữ nghĩa (semantic drift) dù độ dài văn bản không đổi.
- **Yêu cầu đối với Agent**: Thêm `detect_embedding_cosine_drift` và `detect_token_frequency_drift` vào `observability/rag_metrics.py`.
- **Đề xuất của Agent**: Đo khoảng cách Cosine Distance so với centroid chuẩn và tính độ lệch Total Variation Distance (TVD) trên phân phối từ vựng.
- **Bằng chứng / Kiểm thử**: `test_bonus_10_rag_metrics_comprehensive` phát hiện chính xác khi vector ngữ nghĩa hoặc từ vựng bị trôi dạt sang miền chủ đề khác.
- **Quyết định**: **Accept**.
