# Báo cáo Sự cố (Incident Report) — Game Day Data Reliability

## Mức độ nghiêm trọng (Severity)
**P1 — Critical (Ảnh hưởng trực tiếp đến Doanh thu CEO Dashboard & AI Support Agent)**

---

## Tóm tắt sự cố (Summary)
Vào ngày Game Day, hệ thống E-Commerce Data Pipeline ghi nhận trạng thái luồng dữ liệu vẫn báo `SUCCESS`, nhưng CEO phát hiện số liệu doanh thu trên Dashboard bị sai lệch bất thường và đội ngũ Chăm sóc khách hàng (Support Agent) phản hồi thông tin chính sách hoàn tiền bị cũ/sai so với tài liệu mới ban hành.

Sau khi kích hoạt hệ thống Data Observability, đội ngũ kỹ thuật đã cô lập 3 nguồn gốc sự cố đồng thời:
1. **Lỗi trùng lặp khóa chính (Duplicate Order ID)** trong luồng nạp đơn hàng dẫn đến nhân bản doanh thu.
2. **Lỗi sụt giảm dung lượng đơn hàng (Partial Ingestion / Volume Drop)** do batch nạp bị thiếu 75% dữ liệu mà không gây lỗi cú pháp SQL.
3. **Lỗi tài liệu Tri thức quá hạn (Stale Knowledge Base)** do file chính sách hoàn tiền không được cập nhật kịp thời trong 3 giờ.

---

## Dấu hiệu phát hiện (Detection)
- **Tín hiệu cảnh báo 1 (Contract & Great Expectations)**: `orders_contract` phát hiện vi phạm `unique` trên cột `order_id` (3 dòng trùng lặp), kích hoạt hành động `action: block` và đẩy SLO Burn Rate lên `1000.00x` (vượt ngưỡng cho phép, kích hoạt Paging Alert).
- **Tín hiệu cảnh báo 2 (Statistical Anomaly Detection)**: Auto Anomaly Detector (MAD / Z-score) phát hiện số dòng đơn hàng giảm đột ngột từ 600 dòng xuống 150 dòng (score: 5.53 > ngưỡng 3.0).
- **Tín hiệu cảnh báo 3 (Freshness Observability)**: `kb_contract` phát hiện độ trễ xuất bản của tài liệu `kb_documents.jsonl` lên đến 190.0 phút, vượt ngưỡng cam kết SLA/SLO 60.0 phút.
- **Thời điểm quan sát đầu tiên**: 2026-08-29T09:37:00Z trong chu kỳ chạy Data Reliability Baseline.

---

## Nguyên nhân gốc rễ (Root Cause)
1. **Dữ liệu Orders**: Bên cung cấp dữ liệu upstream gửi nhầm bản ghi lặp lại không có deduplication tại tầng staging; đồng thời luồng nạp ngắt quãng khiến chỉ 25% dữ liệu được ghi nhận vào file `orders.csv`.
2. **Dữ liệu SCD Customers**: Chiều dữ liệu khách hàng (`stg_customers`) tồn tại nhiều bản ghi cùng có cờ `is_active = true`, khiến câu lệnh `left join` trong `fct_daily_revenue.sql` nhân đôi số tiền đơn hàng nếu không có cơ chế lọc dòng mới nhất.
3. **Dữ liệu Knowledge Base**: Tiến trình đồng bộ tài liệu chính sách từ CMS nội bộ vào `kb_documents.jsonl` bị nghẽn worker, khiến vector database index giữ phiên bản policy cũ.

---

## Bằng chứng thu thập (Evidence)
1. **Kết quả kiểm tra Contract (`src/contract_validator.py`)**:
   - `orders_contract`: vi phạm `check="unique"`, `column="order_id"`, `severity="critical"`, `action="block"`.
   - `kb_contract`: vi phạm `check="freshness"`, `delay_minutes=190.0 > 60.0`, `action="warn"`.
2. **Kết quả kiểm tra dbt (`dbt build`)**:
   - Generic test `unique_stg_orders_order_id` thất bại khi có dữ liệu duplicate.
   - Singular test `assert_daily_revenue_matches_completed_orders` phát hiện chênh lệch giữa tổng tiền trong staging và marts.
   - dbt Unit test `test_multiple_active_customer_versions_does_not_inflate_revenue` xác nhận khả năng phòng thủ lạm phát doanh thu.
3. **Chỉ số Anomaly & SLO (`observability/`)**:
   - Anomaly detector: `is_anomaly=True`, `method="auto:mad"`, `score=5.53` khi sụt giảm lượng bản ghi.
   - Multi-window SLO Burn Rate: ngắn hạn và dài hạn đều vượt ngưỡng `14.4x`, gửi tín hiệu `page=True`.

---

## Phạm vi ảnh hưởng (Blast Radius)

Dựa trên thuật toán duyệt đồ thị **BFS Transitive Lineage Traversal**:

```text
Dataset-level Blast Radius:
raw_orders -> stg_orders -> fct_daily_revenue -> ceo_revenue_dashboard

Column-level Blast Radius:
raw_orders.amount -> stg_orders.amount_usd -> fct_daily_revenue.daily_revenue -> ceo_revenue_dashboard.revenue

RAG & AI Support Blast Radius:
kb_documents -> kb_active_docs -> rag_index -> support_agent.answer
```

---

## Biện pháp giảm thiểu (Mitigation)
1. **Chặn luồng dữ liệu lỗi (Data Quarantine & Blocking)**: Tự động kích hoạt cơ chế `action: block` tại tầng Contract Validator để ngăn dữ liệu hỏng đổ vào `stg_orders` và `fct_daily_revenue`.
2. **Khắc phục tầng Marts (dbt Protection)**: Cập nhật model `fct_daily_revenue.sql` với subquery `row_number() over (partition by customer_id order by valid_from desc) = 1` để loại bỏ duplicate khi join khách hàng.
3. **Cập nhật lại tài liệu KB**: Kích hoạt lại pipeline đồng bộ chính sách hoàn tiền mới nhất và tái lập chỉ mục (re-index) vector embeddings.

---

## Phục hồi (Recovery)
1. Chạy quy trình reset lab và khôi phục dữ liệu sạch: `python scripts/reset_lab.py`.
2. Đồng bộ seeds và xây dựng lại dbt warehouse: `python scripts/sync_dbt_seeds.py` & `dbt build`.
3. Kiểm tra lại toàn bộ chỉ số baseline: `python scripts/run_baseline.py`.

---

## Xác minh phục hồi (Verification Checklist)
- [x] **Contract Healthy**: 100% kiểm tra hợp đồng dữ liệu đạt (`failed_checks = 0`, `action = allow`).
- [x] **dbt Tests Healthy**: 19/19 checks (seeds, views, tables, data tests, singular tests, unit tests) đều `PASS`.
- [x] **Anomaly Range**: Khối lượng đơn hàng và độ dài văn bản KB nằm trong ngưỡng phân phối bình thường.
- [x] **SLO Healthy**: Error budget còn lại 100%, Burn rate = 0.0x, Multi-window alert `page = False`.
- [x] **Downstream Output Verified**: Doanh thu trên `fct_daily_revenue` khớp chính xác 100% với các đơn hàng `completed`.

---

## Hành động phòng ngừa (Prevention / Action Items)

| Hành động (Action) | Người phụ trách (Owner) | Hạn chót (Deadline) | Mục đích (Why) |
|---|---|---|---|
| Tích hợp Contract Validator vào CI/CD Ingestion Worker | Data Platform Team | Tuần 1 | Chặn dữ liệu sai schema/type/freshness ngay tại cổng nạp |
| Thiết lập cảnh báo Multi-window Burn Rate vào PagerDuty/Slack | SRE / Observability | Tuần 1 | Cảnh báo kịp thời sustained fast burn mà không bị spam bởi transient spikes |
| Chuẩn hóa dbt Unit Testing cho tất cả các mô hình Marts tài chính | Analytics Engineering | Tuần 2 | Ngăn ngừa lỗi nhân bản doanh thu khi thay đổi logic SCD |
| Giám sát tự động độ lệch Embedding Space Drift cho RAG | AI Reliability Team | Tuần 2 | Đảm bảo Chatbot Support không sử dụng thông tin chính sách trôi dạt |
