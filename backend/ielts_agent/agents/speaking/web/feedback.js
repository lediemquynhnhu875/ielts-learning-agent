/* Shared acoustic feedback and sourced rubric lookup. All provider text is data. */
window.SpeakingFeedback = {
  configure(prefix, config) {
    const checkbox = document.getElementById(`${prefix}pronunciation-consent`);
    checkbox.disabled = !config?.configured;
    document.getElementById(`${prefix}pronunciation-config`).textContent = config?.configured
      ? "Chỉ gửi tới Azure khi chọn ô này và bấm gửi câu trả lời. Feedback 0–100, chưa phải band IELTS."
      : "Azure chưa được cấu hình trên backend. Vẫn có thể thu âm và lấy transcript.";
  },
  render(container, result) {
    container.replaceChildren();
    if (!result || result.status === "not_requested") return;
    const heading = document.createElement("h3"); heading.textContent = "Feedback phát âm · Azure"; container.append(heading);
    if (result.status !== "assessed") {
      const p = document.createElement("p"); p.textContent = ({not_configured: "Azure chưa cấu hình.", unavailable: "Azure chưa xử lý được bản thu. Transcript vẫn được giữ.", no_speech: "Chưa có đủ dữ liệu âm thanh để đánh giá."})[result.status] || "Chưa có kết quả phát âm.";
      container.append(p); return;
    }
    const p = document.createElement("p");
    const labels = {accuracy: "Độ chính xác", fluency: "Độ trôi chảy", prosody: "Ngữ điệu", pronunciation: "Phát âm"};
    p.textContent = Object.entries(result.scores).map(([key, value]) => `${labels[key] || key}: ${value == null ? "—" : value + "/100"}`).join(" · ");
    container.append(p);
    const note = document.createElement("p"); note.className = "muted";
    note.textContent = "Trung bình các đoạn theo số từ. Chưa hiệu chỉnh band IELTS; tên riêng/từ tiếng Việt cần nghe lại."; container.append(note);
    const details = document.createElement("details"), summary = document.createElement("summary"); summary.textContent = "Dẫn chứng từ / âm vị trên audio"; details.append(summary);
    for (const segment of result.segments) {
      const text = document.createElement("p"); text.textContent = `Azure nhận dạng riêng: ${segment.recognized_text}`; details.append(text);
      for (const word of segment.words) {
        const item = document.createElement("p");
        item.textContent = `${word.start_s.toFixed(2)}–${word.end_s.toFixed(2)} s · ${word.word}: ${word.accuracy ?? "—"}/100 · ${word.error_type} · ${word.phonemes.map(p => `${p.phoneme}: ${p.accuracy ?? "—"}`).join(", ")}`;
        details.append(item);
      }
    }
    container.append(details);
    for (const chunk of result.rubric_context || []) {
      if (!/^https:\/\//.test(chunk.source_url || "")) continue;
      const link = document.createElement("a"); link.href = `${chunk.source_url}#page=${chunk.page || 1}`;
      link.target = "_blank"; link.rel = "noopener noreferrer";
      link.textContent = `Tham khảo rubric PR band ${chunk.band} (chưa phải band của bạn) · `; container.append(link);
    }
  }
};
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("rubric-form");
  if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const target = document.getElementById("rubric-results"); target.textContent = "Đang tìm rubric…";
    try {
      const response = await fetch("/api/speaking/rubric/search", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({query: document.getElementById("rubric-query").value, criterion: document.getElementById("rubric-criterion").value})});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Chưa đọc được rubric.");
      if (!Array.isArray(data.chunks)) throw Error("Phản hồi tra rubric thiếu danh sách chunks. Hãy khởi động lại backend và tải lại trang để đồng bộ phiên bản.");
      target.replaceChildren();
      if (!data.chunks.length) target.textContent = "Không có dẫn chứng phù hợp trong rubric Speaking. Thử mô tả đặc điểm bằng tiếng Anh.";
      for (const chunk of data.chunks) {
        const detail = document.createElement("details"), summary = document.createElement("summary"), text = document.createElement("p"), source = document.createElement("a");
        summary.textContent = `${chunk.criterion} · Band ${chunk.band ?? "—"} · ${chunk.chunk_id}`; text.textContent = chunk.text;
        if (chunk.source_url && /^https:\/\//.test(chunk.source_url)) { source.href = `${chunk.source_url}#page=${chunk.page || 1}`; source.target = "_blank"; source.rel = "noopener noreferrer"; }
        source.textContent = `Nguồn chính thức · trang ${chunk.page || "—"} · ${chunk.version}`;
        detail.append(summary, text, source); target.append(detail);
      }
    } catch (error) { target.textContent = error.message; }
  });
});
