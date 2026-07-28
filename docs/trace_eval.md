# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)
*Dành cho Role 5: Observability & Reviewer*
*Đề tài lựa chọn*: **Đề 10 - Trợ Lý Tìm & Đặt Lịch Xem Nhà Trọ / Căn Hộ Cho Thuê**

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX - MỐC 1)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá bài toán Đề 10 |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `5/5` | Cần phân tích yêu cầu thuê (khu vực, mức giá, tiện ích) ➔ Lọc phòng ➔ Kiểm tra lịch trống của chủ nhà ➔ Sắp xếp lịch hẹn phù hợp. |
| 🛠️ **Tool Interaction** | `5/5` | Bắt buộc tương tác với dữ liệu thực tế qua Tools: tra cứu danh sách phòng trọ (`search_apartments`), kiểm tra lịch rảnh (`check_viewing_schedule`), và thực hiện đặt lịch xem nhà (`book_viewing_slot`). |
| 🔀 **Dynamic Decision** | `4/5` | Kết quả từ bước tra cứu quyết định bước tiếp theo (VD: Nếu phòng mong muốn đã hết lịch xem cuối tuần, Agent phải linh hoạt gợi ý khung giờ khác hoặc căn hộ tương đương ở cùng khu vực). |
| ⏳ **Long Horizon** | `4/5` | Quy trình gồm nhiều bước liên tiếp: Tìm kiếm ➔ Lọc tiêu chí ➔ Xác nhận tình trạng ➔ Đặt lịch xem ➔ Gửi xác nhận đặt lịch. |
| **TỔNG ĐIỂM FIT** | **18/20** | **KẾT LUẬN: BÀI TOÁN RẤT NÊN DÙNG REACT AGENT!** (Chatbot thông thường không có công cụ tra cứu dữ liệu thời gian thực hay thực hiện thao tác đặt lịch). |

---

## 🔍 2. SO SÁNH PHẢN HỒI (TEST CASE #3 - ĐỀ TÀI 10)

**Câu hỏi**: *"Tôi muốn tìm phòng trọ khu vực Cầu Giấy giá dưới 5 triệu có điều hòa, và đặt lịch xem phòng vào chiều thứ 7 này."*

### 🤖 Chatbot Baseline (Sẽ cập nhật ở Mốc 2):
* **Phản hồi**: *(Chờ Role 4 chạy Baseline Chatbot để ghi nhận)*
* **Nhận xét**: *(Chờ cập nhật)*

### 🧠 ReAct Agent (Sẽ cập nhật ở Mốc 3):
* **Thought 1**: *(Chờ Role 4 chạy ReAct Agent để trích xuất trace log)*
* **Action 1**: 
* **Observation 1**: 
* **Final Answer**: 
* **Nhận xét**: 

