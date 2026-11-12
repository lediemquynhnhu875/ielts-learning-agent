# Migration PostgreSQL tự động

Backend tự thêm bảng và áp dụng SQL migration còn thiếu khi khởi động, trước khi
nhận request. Chỉ cần PostgreSQL đang chạy, database đã được tạo và `DATABASE_URL`
đúng; không cần chạy `init` trước mỗi lần mở ứng dụng. Docker Compose tạo database
và giữ volume; schema do API quản lý.

## Cấu hình và chạy

```powershell
docker compose up -d --wait
python -m uvicorn ielts_agent.api.main:app --host 127.0.0.1 --port 8000
```

`DATABASE_AUTO_MIGRATE` mặc định `true`. Giá trị bật: `true`, `1`, `yes`, `on`;
giá trị tắt: `false`, `0`, `no`, `off`, không phân biệt hoa/thường. Rỗng dùng mặc
định; giá trị khác bị từ chối.

Khi muốn chạy migration bằng bước riêng:

```powershell
$env:DATABASE_AUTO_MIGRATE = 'false'
python -m ielts_agent.infrastructure.db.cli init
python -m uvicorn ielts_agent.api.main:app --host 127.0.0.1 --port 8000
```

Tắt tự động không tự tạo bảng; phải chạy CLI trước khi sử dụng API cần database.

## Cách áp dụng

File SQL nằm trong `backend/ielts_agent/infrastructure/db/sql/`, chạy theo tên:
`001_uc04.sql`, `002_practice.sql`, tiếp theo là `003_<ten-thay-doi>.sql`.

Bảng `uc04_schema_migration` lưu tên file, SHA-256 nội dung và `applied_at`.
Runner kiểm tra lịch sử, chạy file chưa áp dụng và ghi nhận trong cùng transaction.
Một advisory lock bảo đảm các process/worker không áp dụng trùng. Không mở kết
nối database lúc import module; việc migration diễn ra trong lifespan startup.

CSDL cũ chưa có ledger được tiếp nhận bằng hai file `001`/`002` hiện có dùng
`CREATE ... IF NOT EXISTS`; nội dung và lượt làm đã lưu được giữ nguyên.
Không mount lại thư mục SQL vào Docker entrypoint vì việc đó có thể chạy trùng
migration với API trên database mới.

## Thêm migration và xử lý lỗi

Thêm file đánh số mới để đổi schema. Không chỉnh sửa/xóa file đã ghi nhận; runner
sẽ từ chối checksum thay đổi hoặc thiếu file lịch sử. Khác biệt CRLF/LF giữa
Windows và Linux không làm đổi checksum.

Migration SQL lỗi sẽ rollback cả batch chưa áp dụng, gồm DDL và ledger. Backend
dừng startup nếu kết nối thất bại, SQL lỗi, file không đọc được, checksum lệch
hoặc gói không chứa migration. Sửa nguyên nhân rồi khởi động lại; CLI `init` dùng
cùng runner và giúp xem lỗi cụ thể. Runner không tạo lại database hay xóa dữ liệu.
