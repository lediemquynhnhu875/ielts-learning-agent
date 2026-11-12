# Cấu trúc dự án

Mỗi use case được tổ chức thành một module agent, có agent điều phối và các vai trò cần thiết cho nghiệp vụ đó. UC-04 đã có phần triển khai; các UC tiếp theo dùng cùng cách tổ chức. Frontend có khu vực riêng; framework giao diện chưa được chọn.

```text
nhom-05/
├── backend/
│   ├── ielts_agent/
│   │   ├── api/
│   │   │   ├── main.py             # Khởi tạo FastAPI, xử lý lỗi, dependency
│   │   │   └── routes/uc04.py      # Route mỏng gọi UC04Agent
│   │   ├── core/
│   │   │   ├── config.py           # Cấu hình dùng chung
│   │   │   └── errors.py           # Lỗi ứng dụng dùng chung
│   │   ├── agents/
│   │   │   └── uc04/
│   │   │       ├── agent.py        # UC04Agent.run: điều phối toàn bộ UC
│   │   │       ├── generator.py    # ItemGenerationAgent.run
│   │   │       ├── solver.py       # BlindSolverAgent.run
│   │   │       ├── safety.py       # ContentSafetyAgent.run
│   │   │       ├── team.py         # UC04Agents: kết nối các vai trò
│   │   │       ├── models.py       # Schema request, draft, solver
│   │   │       ├── ports.py        # Contract dependency cho UC-04
│   │   │       ├── rules.py        # Validator quy tắc bằng code
│   │   │       ├── validation.py   # Đối chiếu kết quả solver
│   │   │       └── skills/
│   │   │           └── reading-item-generation/SKILL.md
│   │   ├── infrastructure/
│   │   │   ├── db/
│   │   │   │   ├── bank.py         # PostgreSQL repository và transaction
│   │   │   │   ├── cli.py          # Chạy migration thủ công khi cần
│   │   │   │   ├── migrations.py   # Ledger, checksum và migration theo thứ tự
│   │   │   │   └── sql/
│   │   │   └── llm/
│   │   │       └── client.py       # JsonLLMClient: OpenAI / DeepSeek
│   │   └── bootstrap.py           # Composition factory kết nối dependency
│   └── tests/
├── frontend/
│   └── README.md                  # Quy ước mở rộng; chưa có ứng dụng UI
├── docs/
├── compose.yaml                   # PostgreSQL 17, host 55432 → container 5432
├── pyproject.toml                 # Cài package và chạy test từ root
└── .env.example
```

`api/routes/uc04.py` chuyển request HTTP sang `UC04Agent.run` và trả kết quả; prompt, quy tắc nghiệp vụ và SQL được giữ trong các module chuyên trách. `agents/uc04` sở hữu prompt/skill, schema, điều phối và validator của UC-04. Ba agent chuyên trách chạy bằng lời gọi model stateless riêng: generator sinh bài, solver tự giải mà không nhận key, safety đánh giá chủ đề và toàn bộ ứng viên.

`infrastructure/llm/client.py` chỉ xử lý gọi provider, JSON, timeout và lỗi kết nối; client dùng chung không chứa prompt nghiệp vụ. `infrastructure/db` triển khai lưu trữ PostgreSQL và transaction. `bootstrap.py` kết nối các implementation với contract trong `ports.py`, cho phép thay bằng fake khi kiểm thử. `core` chứa cấu hình và lỗi dùng chung. Cách tách này dùng dependency injection và contract trực tiếp, không thêm một framework base-agent khi chưa có nhu cầu.

FastAPI lifespan mặc định gọi `Bank.initialize()` trong worker thread trước khi phục vụ request. `infrastructure/db/migrations.py` áp dụng các SQL còn thiếu dưới advisory lock, ghi phiên bản/checksum trong `uc04_schema_migration` cùng transaction. Migration lỗi sẽ dừng startup; tài nguyên agent được đóng cả khi startup thất bại. Có thể tắt bằng `DATABASE_AUTO_MIGRATE=false` và dùng CLI riêng; xem [migration CSDL](database-migrations.md).

Luồng [làm bài Reading/Listening](reading-listening-practice.md) có adapter `api/routes/practice.py`, schema/contract và dịch vụ trong `practice/`, cùng repository `infrastructure/db/practice.py`. `practice/grading.py` chấm theo đáp án bằng code; không gọi agent/LLM. Repository lưu bản chụp nội dung/key, nháp và kết quả qua `002_practice.sql`, dùng transaction và row lock để bảo vệ nộp đồng thời. `api/main.py` kết nối dependency mới, giữ nguyên các route UC-04.

Khi thêm UC-05, tạo `agents/uc05/` với agent điều phối, vai trò, schema và công cụ riêng cần cho UC đó; thêm route tương ứng và cấu hình dependency tại composition factory. Các phần kết nối LLM/CSDL thực sự dùng chung được tái sử dụng từ `infrastructure`, còn prompt và quyết định nghiệp vụ thuộc agent của UC. Các nghiệp vụ Writing/Speaking và cá nhân hoá không bị thay đổi để phục vụ UC-04. Schema nội dung theo [DATABASE_CONTEXT.md](../DATABASE_CONTEXT.md); phần chưa đủ đặc tả không được bổ sung ngầm.

Frontend sẽ gọi contract HTTP và không truy cập PostgreSQL hay API key của model trực tiếp. Quy ước phát triển tiếp nằm trong [frontend/README.md](../frontend/README.md). Lệnh cài đặt vẫn chạy từ root bằng `python -m pip install -e '.[dev]'`; setuptools tìm package trong `backend/`, pytest tìm test trong `backend/tests`.
