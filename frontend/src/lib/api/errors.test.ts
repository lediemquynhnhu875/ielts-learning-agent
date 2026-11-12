import { describe, expect, it } from "vitest";
import { toApiError } from "./errors";

const TRACE = "5b0c2a7e-1f4d-4c8a-9d3e-2a6b7c8d9e0f";

describe("toApiError", () => {
  it("giữ thông báo tiếng Việt và mã trace của lỗi sinh bài (400, 422)", () => {
    const unsafe = toApiError(400, {
      error: "unsafe_topic",
      message: "Chủ đề không phù hợp; hãy chọn một chủ đề học thuật khác.",
      trace_id: TRACE,
    });
    expect(unsafe).toMatchObject({ status: 400, code: "unsafe_topic", traceId: TRACE });
    expect(unsafe.message).toBe("Chủ đề không phù hợp; hãy chọn một chủ đề học thuật khác.");

    const exhausted = toApiError(422, {
      error: "generation_exhausted",
      message: "Không thể tạo bài đã kiểm chứng sau 3 lần sinh.",
      trace_id: TRACE,
    });
    expect(exhausted.message).toBe("Không thể tạo bài đã kiểm chứng sau 3 lần sinh.");
  });

  it("hiện nguyên văn thông điệp của provider_error (quyết định #7, không còn ngoại lệ)", () => {
    const err = toApiError(503, { error: "provider_error", message: "Model đang quá tải, thử lại sau.", trace_id: TRACE });
    expect(err.message).toBe("Model đang quá tải, thử lại sau.");
    expect(err).toMatchObject({ code: "provider_error", traceId: TRACE });
  });

  it("hiện nguyên văn detail tiếng Việt (Speaking, route trung gian)", () => {
    expect(toApiError(409, { detail: "Phiên đã kết thúc." }).message).toBe("Phiên đã kết thúc.");
    expect(toApiError(413, { detail: "File quá lớn. Giới hạn audio là 24 MB." }).message).toBe(
      "File quá lớn. Giới hạn audio là 24 MB.",
    );
  });

  it("Writing trả lỗi trong khoá error không kèm message: hiện nguyên văn nếu là câu tiếng Việt", () => {
    expect(toApiError(400, { error: "Request quá lớn hoặc rỗng" }).message).toBe("Request quá lớn hoặc rỗng");
    expect(toApiError(403, { error: "Origin rejected" }).message).toBe("Lỗi không xác định (HTTP 403).");
  });

  it("thông điệp lỗi của route trung gian (502, 504) hiện nguyên văn", () => {
    expect(toApiError(502, { error: "backend_unreachable", message: "Không kết nối được backend." }).message).toBe(
      "Không kết nối được backend.",
    );
  });

  it("giữ thông báo CSDL chưa sẵn sàng (503 database_unavailable)", () => {
    const err = toApiError(503, { error: "database_unavailable", message: "PostgreSQL chưa sẵn sàng." });
    expect(err.message).toBe("PostgreSQL chưa sẵn sàng.");
  });

  it("dịch các lỗi HTTP chung sang tiếng Việt", () => {
    expect(toApiError(404, { detail: "Exercise not found" }).message).toBe("Không tìm thấy bài.");
    expect(toApiError(401, { detail: "Invalid bearer token" }).message).toMatch(/token/i);
    expect(toApiError(422, { detail: [{ loc: ["body", "topic"] }] }).message).toBe("Yêu cầu không hợp lệ.");
  });

  it("báo không kết nối được khi không có phản hồi (status 0) hoặc body lạ", () => {
    expect(toApiError(0, null).message).toBe("Không kết nối được backend.");
    expect(toApiError(500, "oops").message).toContain("500");
  });
});
