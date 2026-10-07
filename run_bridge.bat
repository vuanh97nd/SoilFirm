@echo off
title SoilFirm Email Bridge
:: 1. Địa chỉ Worker Cloudflare của bạn (bỏ dấu gạch chéo / ở cuối)
set SOILFIRM_API_BASE=https://soilfirm-api.vuanh97nd.workers.dev

:: 2. Tài khoản và mật khẩu Admin hệ thống
set SOILFIRM_ADMIN_USER=admin
set SOILFIRM_ADMIN_KEY=P2ss@2026

:: 3. Email dịch vụ gửi tin và Mật khẩu ứng dụng 16 ký tự vừa tạo
set SUPPORT_MAIL_USER=email_dich_vu_cua_ban@gmail.com
set SUPPORT_MAIL_PASSWORD=abcdefghijklmnop

:: 4. File lưu trữ lịch sử phản hồi để không gửi lặp
set SUPPORT_STATE_DB=support_mail.sqlite3

python email_bridge.py
pause