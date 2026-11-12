# Chấm thật qua OpenRouter

1. Tạo key tại https://openrouter.ai/settings/keys.
2. Xem model ID tại https://openrouter.ai/models. Chọn model hỗ trợ JSON;
   A/B nên là hai model khác nhau, moderator có thể là model thứ ba.
3. Chạy `python setup_openrouter.py`, nhập key ẩn trong terminal và ba model ID.
   Hoặc copy .env.example thành .env rồi điền OPENROUTER_API_KEY và ba MODEL.
   Không dán key vào chat. Script chỉ lưu local, không gọi API.
4. Nhập rubric chính thức theo README, tạo rubric.json. Không có rubric thì Live từ chối chấm.
5. Dừng server (Ctrl+C), chạy lại `python app.py` hoặc `powershell -File run.ps1`.
6. Mở http://127.0.0.1:8765, chọn Live và nộp bài.

App tự đọc .env cạnh app.py; biến môi trường có sẵn được ưu tiên. Key không gửi về
trình duyệt hay trace. Một bài gọi A, B, feedback (model A), có thể thêm moderator
và retry. Không mặc định model miễn phí đủ hạn mức hoặc vẫn khả dụng.

Endpoint: https://openrouter.ai/api/v1/chat/completions. App dùng JSON output và
provider.require_parameters=true, không tự đổi sang demo nếu model lỗi.
Nguồn: https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request

Nếu python không có trong PATH trên máy hiện tại:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 setup_openrouter.py
```

Chưa gọi provider thật trong phiên phát triển: cần key và model của bạn. Chưa
đồng bộ Planning hoặc đánh giá chất lượng bằng dataset có điểm giáo viên.
