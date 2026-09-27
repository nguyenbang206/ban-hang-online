@echo off
chcp 65001 > nul
title HỆ THỐNG QUẢN LÝ BÁN HÀNG TÍCH HỢP AI • ICTU 2026
echo ================================================================
echo    HỆ THỐNG QUẢN LÝ BÁN HÀNG CÓ TÍCH HỢP AI (LAPTOP & PHỤ KIỆN)
echo    Nhóm 01: Nguyễn Đình Bằng, Vàng Thị Dẳm
echo    Khoa CNTT - Trường ĐH CNTT và Truyền thông Thái Nguyên (ICTU)
echo ================================================================
echo.
echo [1/2] Đang kiểm tra cơ sở dữ liệu SQLite...
python backend\database.py
if errorlevel 1 (
    echo [LỖI] Không thể khởi tạo CSDL!
    pause
    exit /b 1
)

echo [2/2] Đang khởi chạy máy chủ Flask Web Server trên cổng 5000...
echo.
echo ================================================================
echo    WEBSITE ĐANG CHẠY TẠI ĐỊA CHỈ: http://localhost:5000
echo    Hãy mở trình duyệt Web (Chrome, Edge) để truy cập!
echo ================================================================
echo.
python backend\app.py
pause
