# HỆ THỐNG QUẢN LÝ BÁN HÀNG CÓ TÍCH HỢP AI (LAPTOP & PHỤ KIỆN)

> **Báo cáo Dự án Học phần**: Ứng dụng Trí tuệ Nhân tạo  
> **Nhóm thực hiện**: Nhóm 01  
> **Sinh viên**: Nguyễn Đình Bằng, Vàng Thị Dẳm  
> **Đơn vị**: Khoa Công nghệ Thông tin – Trường Đại học CNTT & Truyền thông Thái Nguyên (ICTU)  
> **Giảng viên hướng dẫn**: ThS. Ngô Hữu Huy  

---

## 1. Giới thiệu Dự án

Dự án được xây dựng bám sát 100% tài liệu đặc tả kỹ thuật trong tệp `BÁN HÀNG CÓ TÍCH HỢP AI.docx`. Hệ thống giải quyết trọn vẹn bài toán kinh doanh bán lẻ laptop và thiết bị công nghệ với đầy đủ 12 Use Case cốt lõi, từ quản lý sản phẩm, tồn kho, bán hàng POS, lập hóa đơn, thống kê báo cáo cho đến 3 chức năng Trí tuệ Nhân tạo đột phá.

### 12 Use Case Triển khai:
- **UC01**: Đăng nhập, đăng xuất và chuyển đổi vai trò linh hoạt (Admin, Manager, Staff, Customer).
- **UC02**: Quản lý sản phẩm Laptop (CPU, RAM, GPU, Ổ cứng, Màn hình, Giá nhập, Giá bán, Trạng thái).
- **UC03**: Quản lý khách hàng (Phân hạng Thân thiết / Bạc / Vàng / Kim cương / Ruby theo tổng chi tiêu, lưu lịch sử giao dịch).
- **UC04**: Lập và quản lý hóa đơn bán hàng POS (chọn món, kiểm tra tồn kho, chiết khấu <= 15%, thanh toán Tiền mặt / VietQR / Thẻ POS, in hóa đơn chuẩn K80/A4).
- **UC05**: Quản lý nhập hàng và tồn kho (lập phiếu nhập, cảnh báo sản phẩm dưới ngưỡng tối thiểu).
- **UC06**: Tìm kiếm, lọc và tra cứu dữ liệu đa tiêu chí.
- **UC07**: Thống kê và báo cáo doanh thu (biểu đồ Chart.js theo ngày và cơ cấu danh mục).
- **UC08**: Xuất báo cáo dữ liệu định dạng chuẩn CSV / Excel.
- **UC09 (AI)**: **AI Tư vấn sản phẩm** (đối sánh kho hàng thực tế, sinh bảng so sánh thông số và gợi ý tối đa 3 laptop phù hợp).
- **UC10 (AI)**: **AI Phân tích & Nhận xét Doanh thu** (đánh giá hiệu quả kinh doanh, cảnh báo hàng bán chậm, gợi ý kế hoạch nhập kho).
- **UC11 (AI)**: **AI Hỏi đáp Dữ liệu Bán hàng** (trả lời ngôn ngữ tự nhiên từ dữ liệu CSDL, chống hallucination).
- **UC12**: Quản lý người dùng & phân quyền tài khoản (Admin Only).

---

## 2. Cấu trúc Thư mục

```
DU_AN_AI/
├── app.py                      # Flask Backend & RESTful APIs
├── database.py                 # SQLite Schema (12 bảng) & Seed Data
├── ai_service.py               # Module xử lý 3 chức năng AI (UC09, UC10, UC11)
├── prompts/                    # Thư mục Prompt Template theo chuẩn
│   ├── product_advisor.txt     # Template cho AI tư vấn
│   ├── revenue_analyst.txt     # Template cho AI phân tích báo cáo
│   └── sales_qa.txt            # Template cho AI hỏi đáp
├── static/
│   ├── css/
│   │   └── style.css           # Giao diện Obsidian Cyber Dark & Glassmorphism
│   └── js/
│       └── app.js              # Xử lý tương tác SPA, POS, Chart.js, AI Calls
├── templates/
│   └── index.html              # Màn hình web tổng hợp 12 phân hệ
├── sales_management.db         # Cơ sở dữ liệu SQLite
├── run.bat                     # File chạy 1-click trên Windows
├── requirements.txt            # Danh sách thư viện Python
├── .env.example                # Cấu hình biến môi trường
└── README.md                   # Tài liệu hướng dẫn sử dụng
```

---

## 3. Hướng dẫn Khởi chạy Hệ thống

### Cách 1: Khởi chạy nhanh 1-Click (Khuyên dùng trên Windows)
1. Mở thư mục dự án `DU_AN_AI`.
2. Nhấp đúp chuột vào tệp **`run.bat`**.
3. Mở trình duyệt web (Google Chrome, Microsoft Edge) và truy cập địa chỉ:
   ```
   http://localhost:5000
   ```

### Cách 2: Khởi chạy bằng dòng lệnh Terminal
```bash
# 1. Khởi tạo CSDL (nếu cần)
python database.py

# 2. Chạy máy chủ Flask
python app.py
```

---

## 4. Tài khoản Đăng nhập & Thử nghiệm Phân quyền

Hệ thống tích hợp thanh **Chuyển vai trò nhanh (Role Switcher)** ngay góc trên cùng bên phải giao diện:
1. **👑 Admin**: Nguyễn Đình Bằng (Toàn quyền quản trị, thêm sửa xóa, cấu hình người dùng).
2. **📈 Quản lý (Manager)**: Vàng Thị Dẳm (Theo dõi KPI, xem báo cáo, sử dụng cả 3 chức năng AI).
3. **🛒 Nhân viên (Staff)**: Trần Văn Bán Hàng (Thao tác quầy POS, tư vấn khách, lập hóa đơn, trừ kho).
4. **👤 Khách hàng (Customer)**: Lê Khách VIP (Xem danh mục máy, nhận tư vấn cấu hình).

---

## 5. Hướng dẫn Chụp ảnh Giao diện cho Mục 2.8 của Báo cáo

Sau khi mở web tại `http://localhost:5000`, bạn có thể chụp các màn hình sau để dán vào file Word báo cáo:
1. **Mục 2.8.1 (Giao diện Tổng quan & Đăng nhập)**: Chụp màn hình **Dashboard KPI** (Biểu đồ doanh thu 7 ngày & cơ cấu danh mục).
2. **Mục 2.8.2 (Giao diện Quản lý sản phẩm)**: Chụp màn hình menu **Sản phẩm & Kho** (Bảng thông số cấu hình CPU/RAM/GPU, trạng thái tồn kho).
3. **Mục 2.8.3 (Giao diện Quản lý khách hàng)**: Chụp màn hình menu **Khách hàng** (Phân hạng VIP, tổng chi tiêu).
4. **Mục 2.8.4 (Giao diện Lập và quản lý hóa đơn)**: Chụp màn hình **Bán hàng POS** và cửa sổ xem trước **Hóa đơn thanh toán kèm mã VietQR**.
5. **Mục 2.8.5 (Giao diện Quản lý nhập hàng và tồn kho)**: Chụp màn hình menu **Nhập hàng** và modal tạo phiếu nhập.
6. **Mục 2.8.6 (Giao diện Tìm kiếm, lọc và tra cứu)**: Chụp thanh công cụ tìm kiếm và các bộ lọc danh mục tại trang POS hoặc Sản phẩm.
7. **Mục 2.8.7 (Giao diện Thống kê và báo cáo doanh thu)**: Chụp màn hình menu **Thống kê & Xuất file**.
8. **Mục 2.8.9 (Giao diện AI tư vấn sản phẩm)**: Chụp màn hình tab **UC09: AI Tư vấn Laptop** (Bảng so sánh 3 cấu hình máy).
9. **Mục 2.8.10 (Giao diện AI phân tích báo cáo doanh thu)**: Chụp màn hình tab **UC10: AI Phân tích Doanh thu**.
10. **Mục 2.8.11 (Giao diện AI hỏi đáp dữ liệu bán hàng)**: Chụp màn hình tab **UC11: AI Hỏi đáp Dữ liệu** (Hộp thoại Chat tương tác thông minh).
11. **Mục 2.8.12 (Giao diện Quản lý người dùng và phân quyền)**: Chụp màn hình menu **Phân quyền & Tài khoản**.
