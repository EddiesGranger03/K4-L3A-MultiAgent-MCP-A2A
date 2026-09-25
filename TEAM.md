# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---|---|---|---|---|---|
| 1 | Nguyễn Khánh Sơn | 2A202602388 | 26ai.sonnk2@vinuni.edu.vn | Nhóm trưởng / Coordinator Agent. Thiết kế luồng kiến trúc, phát triển Coordinator, điều phối handoff giữa các agent, kiểm thử hệ thống tổng (`day09 run`). | Báo cáo kiến trúc hệ thống và kết quả tích hợp toàn cục. |
| 2 | Lê Châu Trần Phát | 2A202602545 | 26ai.phatlct@vinuni.edu.vn | Order/Item Agent & Refund Agent. Xây dựng logic gọi MCP `get_order`, `get_order_items`, `get_refund_timeline`. Xác minh trạng thái đơn, seller và quá trình hoàn tiền. | Báo cáo module xử lý thông tin đơn hàng và đối soát hoàn tiền. |
| 3 | Nguyễn Nam Khánh | 2A202602568 | 26ai.khanhnn@vinuni.edu.vn | Payment Agent & Shipment Agent. Phân tích `get_payment_timeline`, `get_shipment_summary`. Phát hiện thanh toán trùng (duplicate charge) và phân tích timeline trễ hạn giao hàng. | Báo cáo module đối chiếu giao dịch thanh toán và lộ trình vận chuyển. |
| 4 | Bùi Thị Thu Uyên | 2A202602613 | 26ai.uyenbtt@vinuni.edu.vn | Policy Agent & Model Triage. Phát triển `ModelTriageClient` gọi OpenRouter API để parse message. Xây dựng Policy Agent kiểm tra rule và đưa ra mức hoàn tiền hợp lệ. | Báo cáo module xử lý ngôn ngữ (LLM triage) và hệ thống áp dụng chính sách. |
| 5 | Ngô Xuân Hoàng | 2A202602597 | 26ai.hoangnx2@vinuni.edu.vn | Verifier Agent & Trace Manager. Kiểm tra claim linkage, evidence refs hợp lệ. Ghi nhận Trace event đúng chuẩn hợp đồng, chuẩn hóa schema output JSON và đóng gói (`day09 package`). | Báo cáo hệ thống kiểm định sự kiện (Verifier) và quản lý vết (Trace). |
