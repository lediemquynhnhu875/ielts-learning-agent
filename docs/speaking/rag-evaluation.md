# Kiểm tra retrieval rubric

20 truy vấn tự soạn: 16 có đáp án, 4 ngoài kho. Nhãn band do người triển khai gán; cần nhóm rà soát độc lập.

| Cấu hình | Hit@3 | MRR@3 | Từ chối đúng câu không đáp án | ms/truy vấn |
| --- | ---: | ---: | ---: | ---: |
| bm25 | 1.000 | 1.000 | 0.750 | 0.079 |
| hybrid_rerank | 1.000 | 1.000 | 0.750 | 0.078 |

Index được dựng một lần, không tính vào latency truy vấn. Đây là kiểm tra tìm rubric, không đo độ chính xác chấm IELTS.

Ca thất bại `none4`: “How does grammatical accuracy influence admission to a university?” không có đáp án trong band descriptors, nhưng hệ thống trả các band [5, 3]. Từ khóa grammar/accuracy trùng rubric không chứng minh có thông tin về tuyển sinh. Bộ lọc phạm vi đơn giản chưa xử lý được câu hỏi quan hệ như vậy; UI là công cụ tra đoạn, không tự tạo câu trả lời tuyển sinh. Cần relevance judge hoặc bộ phân loại no-answer được kiểm thử độc lập trước khi dùng như chatbot hỏi đáp mở.

Hạn chế: reranker tuyến tính cục bộ, chưa phải cross-encoder; hỗ trợ truy vấn tiếng Anh; câu hỏi ngoài kho có từ trùng rubric vẫn có thể gây false positive. Cần thêm câu hỏi ngoài kho khó và nhãn của giáo viên.
