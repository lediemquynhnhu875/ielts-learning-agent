"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  let snapshot = null, busy = false, recorder = null, stream = null, chunks = [], blob = null, audioUrl = null;
  let recordingAt = 0, recordedQuestion = null, lastQuestion = null, preparingMic = false, autoStarting = false;
  let capability = null, receivedAt = Date.now();
  const clock = (seconds) => `${String(Math.floor(Math.max(0, seconds) / 60)).padStart(2, "0")}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, "0")}`;
  const session = () => snapshot?.session;
  const endpoint = (suffix = "") => `/api/exam/sessions/${session().id}${suffix}`;
  function error(message = "") { el("exam-error").textContent = message; el("exam-error").hidden = !message; }
  function gradingProgress(message, failed = false) {
    el("grading-progress").textContent = message;
    el("grading-progress").hidden = !message;
    el("grading-progress").classList.toggle("error", failed);
  }
  function showGradingResult(result) {
    session().assessment = result.assessment;
    session().last_grading_attempt = result.last_grading_attempt || null;
    renderAssessment(result.assessment);
    if (result.regrade_failed) gradingProgress(`${result.message} ${(result.regrade_errors || []).join(" · ")}`, true);
    else if (!result.last_grading_attempt) gradingProgress(result.retryable
      ? "Chưa chấm được. Hãy xem lỗi và thử lại sau."
      : "Đang hiển thị bản chấm đã lưu. Dùng Chấm lại bằng loop mới để tạo bản mới.", Boolean(result.retryable));
    el("grading-progress").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let data;
    try { data = await response.json(); } catch { throw new Error("Không đọc được phản hồi backend."); }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Dữ liệu chưa hợp lệ. Hãy kiểm tra câu trả lời.");
    return data;
  }
  const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  async function work(action) {
    if (busy) return;
    busy = true; error(); controls();
    try { await action(); } catch (e) { error(e.message); }
    finally { busy = false; controls(); }
  }
  function accept(data) {
    if (!data?.session || !Array.isArray(data.session.speaking_turns) || !Array.isArray(data.answers)) {
      throw new Error("Phản hồi phiên thi thiếu speaking_turns hoặc answers. Hãy khởi động lại backend và tải lại trang để đồng bộ phiên bản; dữ liệu phiên vẫn được giữ trên backend.");
    }
    snapshot = data; capability = data.capabilities || capability;
    receivedAt = Date.now();
    localStorage.setItem("speaking-exam-session", session().id);
    render();
  }
  function controls() {
    el("exam-pronunciation-consent").disabled = busy || !capability?.pronunciation?.configured;
    const s = session(), isRecording = recorder?.state === "recording";
    const active = s?.status === "in_progress", unavailable = busy || preparingMic || !active;
    el("start-exam").disabled = busy;
    for (const id of ["exam-submit", "exam-prepare", "exam-speak", "exam-preview", "exam-file", "exam-text", "exam-vocabulary"]) el(id).disabled = unavailable || isRecording;
    el("exam-submit").disabled ||= s?.mode === "voice" && !blob;
    el("exam-submit").textContent = busy ? "Đang xử lý…" : "Gửi câu trả lời →";
    el("exam-record").disabled = busy || preparingMic || !active;
    el("exam-record").textContent = isRecording ? "Dừng ghi âm" : "Bắt đầu ghi âm";
    el("exam-pause").disabled = busy || preparingMic || isRecording || !s || s.status === "finished";
    el("exam-pause").textContent = s?.status === "paused" ? "Tiếp tục phiên" : "Tạm dừng";
    el("exam-reload").disabled = busy || preparingMic || isRecording;
    el("exam-new").disabled = busy || preparingMic || isRecording;
    el("use-voice").disabled = el("stale-reload").disabled = busy;
    el("paused-resume").disabled = busy || preparingMic;
    if (s?.mode === "voice" && !isRecording) {
      el("voice-status").textContent = s.status === "paused"
        ? "Phiên đang tạm dừng. Bấm Tiếp tục làm bài trước khi ghi âm."
        : blob
          ? "Đã có bản thu cho câu này. Nghe lại rồi bấm Gửi câu trả lời để gửi tới Groq."
          : "Chưa có bản thu. Bấm Bắt đầu ghi âm hoặc Chọn audio, rồi mới gửi được câu trả lời.";
    }
    el("exam-grade").disabled = busy || !capability?.grading_ready;
    el("exam-regrade").disabled = busy || !capability?.grading_ready || s?.status !== "finished";
    el("session-save-audio").disabled = busy || preparingMic || isRecording || s?.mode !== "voice" || s?.status === "finished";
    el("exam-download-draft").hidden = !audioUrl;
    if (audioUrl) {
      el("exam-download-draft").href = audioUrl;
      const type = blob?.type || "";
      const extension = type.includes("mp4") ? "m4a" : type.includes("mpeg") ? "mp3" : type.includes("wav") ? "wav" : type.includes("ogg") ? "ogg" : type.includes("flac") ? "flac" : "webm";
      el("exam-download-draft").download = blob?.name || `speaking-answer.${extension}`;
    }
    el("exam-export").disabled = busy;
    el("another-exam").disabled = busy;
    if (s?.current_question?.kind === "long_turn") {
      el("exam-prepare").disabled ||= s.phase !== "ready";
      el("exam-speak").disabled ||= s.phase === "speaking";
    }
  }
  function render() {
    const s = session(), q = s.current_question;
    el("setup").hidden = true; el("exam-active").hidden = false;
    el("exam-capabilities").textContent = capability.limitations;
    el("session-mode").textContent = `${s.kind === "mock" ? "Thi thử · ghi âm" : "Luyện tập · gõ chữ"} · ${s.save_audio ? "Có lưu audio" : "Không lưu audio"}`;
    el("session-audio-option").hidden = s.mode !== "voice" || s.status === "finished";
    el("session-save-audio").checked = Boolean(s.save_audio);
    const savedAudio = snapshot.answers.filter((a) => a.audio_uri).length;
    el("audio-storage-note").textContent = s.mode === "voice"
      ? `Có audio của ${savedAudio}/${snapshot.answers.length} câu đã gửi. Mở từng câu bên dưới để nghe hoặc tải. Audio của câu chưa được lưu không thể khôi phục; bật lưu chỉ áp dụng cho các lượt tiếp theo.`
      : "Phiên gõ chữ không có audio.";
    el("exam-download-all").hidden = !snapshot.answers.length || savedAudio !== snapshot.answers.length;
    el("exam-download-all").href = endpoint("/attempt-audio");
    el("checkpoint-status").textContent = s.status === "paused" ? "Đã tạm dừng. Có thể đóng trang và tiếp tục sau." : s.status === "finished" ? "Đã hoàn thành và lưu phiên." : `Đã lưu ${s.speaking_turns.length} câu trả lời.`;
    document.querySelectorAll("[data-part]").forEach((node) => node.classList.toggle("active", node.dataset.part === s.part));
    el("exam-part").textContent = s.status === "finished" ? "HOÀN THÀNH" : `${s.part.toUpperCase()} · ${s.status === "paused" ? "TẠM DỪNG" : q.kind === "long_turn" ? "BÀI NÓI DÀI" : "THẢO LUẬN"}`;
    el("exam-count").textContent = `${s.speaking_turns.length} / tối đa ${s.turn_limit} lượt`;
    el("exam-question").textContent = q?.text || "Bạn đã hoàn thành phiên thi.";
    el("exam-cue").replaceChildren();
    for (const point of q?.points || []) { const item = document.createElement("li"); item.textContent = point; el("exam-cue").append(item); }
    el("exam-explain").textContent = q?.explain || "";
    el("exam-grounding").hidden = !q?.refs_point_id;
    el("exam-grounding").textContent = q?.refs_point_id ? "Câu hỏi đào sâu từ một ý bạn đã nêu trong câu trả lời trước." : "";
    el("exam-notice").hidden = !s.notice; el("exam-notice").textContent = s.notice;
    el("exam-preparation").hidden = q?.kind !== "long_turn";
    // A checkpoint saved before the mock exam became voice-only can still be
    // resumed, but it must not offer a text box the backend now refuses.
    const stale = s.kind === "mock" && s.mode !== "voice";
    el("text-answer").hidden = s.mode !== "text" || !q || stale;
    el("stale-mode").hidden = !stale || !q;
    // Every control is disabled while paused, so say so where the controls are.
    el("paused-banner").hidden = s.status !== "paused";
    el("voice-answer").hidden = s.mode !== "voice" || !q;
    el("exam-vocabulary-wrap").hidden = s.mode !== "voice" || !q;
    el("exam-pronunciation-wrap").hidden = s.mode !== "voice" || !q;
    el("exam-submit").hidden = el("exam-pause").hidden = el("exam-preview").hidden = !q || stale;
    if (q?.question_id !== lastQuestion) {
      el("exam-text").value = ""; el("exam-notes").value = "";
      clearAudio(); lastQuestion = q?.question_id;
    }
    renderHistory(); renderAssessment(s.assessment); tick(); controls();
  }
  function renderHistory() {
    el("exam-history").replaceChildren();
    for (const a of snapshot.answers) {
      const answerFlags = Array.isArray(a.flags) ? a.flags : [];
      const li = document.createElement("li"), detail = document.createElement("details"), summary = document.createElement("summary"), p = document.createElement("p");
      summary.textContent = `${a.question.part.toUpperCase()} · ${a.response.split(/\s+/).length} từ${answerFlags.length ? " · cần xem lại" : ""}`;
      p.textContent = a.response; detail.append(summary, p);
      const feedback = document.createElement("div"); SpeakingFeedback.render(feedback, a.analysis?.pronunciation); detail.append(feedback);
      if (answerFlags.length) { const flags = document.createElement("p"); flags.className = "muted"; flags.textContent = answerFlags.join(" · "); detail.append(flags); }
      if (a.audio_uri) {
        const player = document.createElement("audio"); player.controls = true; player.preload = "none"; player.src = a.audio_uri;
        const download = document.createElement("a"); download.className = "button secondary";
        download.href = `${a.audio_uri}?download=true`; download.download = ""; download.textContent = "Tải audio câu này";
        detail.append(player, download);
      }
      li.append(detail); el("exam-history").append(li);
    }
  }
  function renderAssessment(a) {
    el("exam-result").hidden = session().status !== "finished";
    if (!a) return;
    const lastAttempt = session().last_grading_attempt;
    if (lastAttempt) gradingProgress(`${lastAttempt.message} ${(lastAttempt.errors || []).join(" · ")}`, lastAttempt.status === "failed");
    el("grading-run").textContent = `Kết quả đang hiển thị · mã lần chấm: ${a.run_id || "chưa chấm"}${lastAttempt?.at ? ` · cập nhật ${new Date(lastAttempt.at).toLocaleString("vi-VN")}` : ""}`;
    const labels = { pending_teacher: "Cần giáo viên xem lại", final: "Giáo viên đã chốt", provisional: "Tạm tính" };
    el("assessment-status").textContent = labels[a.status] || "Tạm tính";
    el("overall").textContent = a.overall_band == null ? "Chưa có điểm tổng"
      : a.status === "final" ? `Band do giáo viên chốt · ${a.overall_band}` : `Band tạm tính · ${a.overall_band}`;
    el("assessment-limitations").textContent = a.limitations;
    el("assessment-disclaimer").textContent = a.disclaimer;
    el("assessment-criteria").replaceChildren();
    for (const row of a.criteria) {
      const card = document.createElement("div"), title = document.createElement("span"), score = document.createElement("strong"), comment = document.createElement("p");
      card.className = "criterion"; title.textContent = row.criterion; score.textContent = row.band ?? "—";
      comment.className = "muted"; comment.textContent = row.comment; card.append(title, score, comment);
      if (row.grader_bands && row.band == null && row.grader_bands.A != null) {
        const split = document.createElement("p"); split.className = "grader-split";
        split.textContent = `A ${row.grader_bands.A} · B ${row.grader_bands.B}`; card.append(split);
      }
      for (const item of row.evidence) { const quote = document.createElement("blockquote"); quote.textContent = `“${item.quote}”`; card.append(quote); }
      for (const source of a.descriptor_sources || []) {
        if (source.criterion !== row.criterion || !/^https:\/\//.test(source.source_url || "")) continue;
        const link = document.createElement("a"); link.href = `${source.source_url}#page=${source.page || 1}`;
        link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = `Rubric band ${source.band} · trang ${source.page || "—"} `;
        card.append(link);
      }
      el("assessment-criteria").append(card);
    }
    el("assessment-feedback").replaceChildren();
    for (const item of a.corrections) {
      const detail = document.createElement("details"), summary = document.createElement("summary"), content = document.createElement("p"), vocab = document.createElement("p");
      summary.textContent = "Gợi ý nâng cấp câu trả lời"; content.textContent = item.upgraded_answer; vocab.textContent = `Từ vựng: ${item.vocabulary.join(", ")}`;
      detail.append(summary, content, vocab); el("assessment-feedback").append(detail);
    }
    for (const message of a.grading_errors || []) { const p = document.createElement("p"); p.className = "notice"; p.textContent = message; el("assessment-feedback").append(p); }
    el("grading-requirements").textContent = capability.grading_ready
      ? `Hai giám khảo chấm độc lập bằng ${capability.grader_model}; offsets dẫn chứng do code tra lại trong transcript trước khi tính điểm. Khi hạn mức token mỗi phút thấp, một lần chấm có thể mất 1–2 phút vì phải chờ.`
      : "Chưa có model chấm điểm hoặc kho Speaking descriptors của nhóm. Bạn vẫn có thể xuất toàn bộ phiên để tích hợp.";
    el("teacher-panel").hidden = a.status !== "pending_teacher";
    if (!el("teacher-panel").hidden && !el("teacher-band-grid").children.length) {
      for (const criterion of ["FC", "LR", "GRA", "PR"]) {
        const wrap = document.createElement("div"), label = document.createElement("label"), input = document.createElement("input");
        label.textContent = criterion; label.htmlFor = `teacher-band-${criterion}`;
        input.id = `teacher-band-${criterion}`; input.type = "number"; input.min = "0"; input.max = "9"; input.step = "0.5";
        wrap.append(label, input); el("teacher-band-grid").append(wrap);
      }
    }
  }
  function renderWeakness(profile) {
    el("weakness-panel").hidden = false;
    const body = el("weakness-body"); body.replaceChildren();
    const head = document.createElement("p"); head.className = "muted";
    head.textContent = profile.status === "ready"
      ? `Yếu nhất: ${profile.weakest_criteria.join(", ")} · chưa chấm: ${(profile.not_assessed || []).join(", ") || "—"}`
      : profile.reason || "Chưa có hồ sơ.";
    body.append(head);
    for (const row of profile.criteria) {
      const card = document.createElement("div"), title = document.createElement("h4"), target = document.createElement("p");
      card.className = "weakness-row";
      title.textContent = `#${row.rank} ${row.criterion} · band ${row.band}`;
      const next = row.next_band_descriptor;
      target.className = "muted";
      target.textContent = next ? `Mốc band ${next.band} theo rubric (${next.chunk_id}): ${next.text}`
        : "Không tìm thấy descriptor cho band kế tiếp trong kho đã cấu hình.";
      card.append(title, target);
      for (const span of row.evidence.slice(0, 2)) {
        const quote = document.createElement("blockquote");
        quote.textContent = `Lượt ${span.turn_number ?? "—"}: “${span.quote}”`; card.append(quote);
      }
      body.append(card);
    }
    const note = document.createElement("p"); note.className = "muted";
    note.textContent = "Hồ sơ này chỉ suy ra từ bản chấm đã qua validator; chưa ghi vào database chung hay hồ sơ Planning Agent của nhóm.";
    body.append(note);
  }
  function clearAudio() {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = null; blob = null; recordedQuestion = null;
    el("exam-playback").pause(); el("exam-playback").removeAttribute("src"); el("exam-playback").hidden = true;
    el("record-clock").textContent = "00:00";
  }
  async function action(name) {
    const data = await api(endpoint("/actions"), json({ action: name, version: session().version }));
    accept(data);
    if (data.message) { el("exam-notice").textContent = data.message; el("exam-notice").hidden = false; }
  }
  async function microphone() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error("Không hỗ trợ microphone. Hãy dùng localhost/HTTPS hoặc chọn audio.");
    if (!stream?.getAudioTracks().some((t) => t.readyState === "live")) stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  }
  function releaseMic() { stream?.getTracks().forEach((t) => t.stop()); stream = null; }
  async function record() {
    if (recorder?.state === "recording") { recorder.stop(); controls(); return; }
    preparingMic = true; controls();
    try {
      await microphone();
      if (session().current_question.kind === "long_turn" && session().phase !== "speaking") await action("speak");
      stream.getAudioTracks().forEach((t) => { t.enabled = true; });
      const mime = ["audio/webm;codecs=opus", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks = []; recordedQuestion = session().current_question.question_id;
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        blob = new Blob(chunks, { type: recorder.mimeType }); audioUrl = URL.createObjectURL(blob);
        el("exam-playback").src = audioUrl; el("exam-playback").hidden = false;
        el("voice-status").textContent = "Bản thu sẵn sàng. Nghe lại trước khi gửi.";
        releaseMic(); controls();
      };
      recorder.onerror = () => { releaseMic(); error("Ghi âm bị gián đoạn. Hãy thu lại."); controls(); };
      recorder.start(250); recordingAt = Date.now();
      el("voice-status").textContent = "Đang ghi âm…";
    } catch (e) { releaseMic(); throw new Error(e.name === "NotAllowedError" ? "Microphone chưa được cấp quyền. Có thể chọn file audio để tiếp tục." : e.message); }
    finally { preparingMic = false; controls(); }
  }
  function tick() {
    const s = session(); if (!s) return;
    const elapsedSession = s.elapsed_seconds + (s.status === "in_progress" ? Math.floor((Date.now() - receivedAt) / 1000) : 0);
    el("elapsed").textContent = `Đã lưu · ${s.speaking_turns.length} câu · ${clock(elapsedSession)}`;
    if (s.current_question?.kind === "long_turn") {
      const remaining = s.status === "paused" ? s.part_time_left : s.phase_deadline ? Math.max(0, Math.ceil(s.phase_deadline - Date.now() / 1000)) : null;
      el("phase-label").textContent = s.phase === "preparing" ? "Chuẩn bị" : s.phase === "speaking" ? (s.mode === "voice" ? "Thời gian nói" : "Thời gian tham khảo · text") : "Chuẩn bị / nói";
      el("exam-clock").textContent = remaining == null ? "01:00 / 02:00" : clock(remaining);
      if (remaining === 0 && s.phase === "preparing" && s.status === "in_progress" && !busy && !autoStarting) {
        autoStarting = true;
        work(async () => { await action("speak"); if (s.mode === "voice") await record(); }).finally(() => { autoStarting = false; });
      }
      if (remaining === 0 && s.phase === "speaking" && recorder?.state === "recording") recorder.stop();
    }
    if (recorder?.state === "recording") {
      const elapsed = (Date.now() - recordingAt) / 1000;
      el("record-clock").textContent = clock(elapsed);
      if (elapsed >= (s.current_question?.kind === "long_turn" ? 120 : 180)) recorder.stop();
    }
  }
  function setupMode() {
    const voice = el("exam-mode").value === "voice";
    el("save-audio").disabled = !voice;
    const missing = voice && capability && capability.stt_ready === false;
    el("setup-stt-warning").hidden = !missing;
    el("setup-stt-warning").textContent = missing
      ? "Chưa cấu hình GROQ_API_KEY nên bản thu không chép lại được. Thêm key vào .env rồi khởi động lại backend, hoặc chọn phiên luyện gõ chữ."
      : "";
  }
  el("exam-mode").onchange = setupMode;
  el("start-exam").onclick = () => work(async () => {
    // Voice is the mock exam; typing is only ever a practice session.
    const mode = el("exam-mode").value;
    accept(await api("/api/exam/sessions", json({ mode, kind: mode === "voice" ? "mock" : "practice", topic_id: el("exam-topic").value, save_audio: el("save-audio").checked })));
  });
  const pauseToggle = () => work(async () => { await action(session().status === "paused" ? "resume" : "pause"); releaseMic(); });
  el("exam-pause").onclick = pauseToggle;
  el("paused-resume").onclick = pauseToggle;
  el("exam-preview").onclick = () => work(() => action("preview_part3"));
  el("exam-prepare").onclick = () => work(async () => {
    if (session().mode === "voice") { await microphone(); stream.getAudioTracks().forEach((t) => { t.enabled = false; }); }
    try { await action("prepare"); } catch (e) { releaseMic(); throw e; }
  });
  el("exam-speak").onclick = () => work(async () => { if (session().mode === "voice") await record(); else await action("speak"); });
  el("exam-record").onclick = () => work(record);
  el("exam-file").onchange = () => {
    const file = el("exam-file").files[0]; el("exam-file").value = "";
    if (!file || busy || session()?.status !== "in_progress" || recorder?.state === "recording") return;
    if (file.size > 24 * 1024 * 1024) { error("Audio vượt giới hạn 24 MB."); return; }
    clearAudio(); blob = file; recordedQuestion = session().current_question.question_id;
    audioUrl = URL.createObjectURL(file); el("exam-playback").src = audioUrl; el("exam-playback").hidden = false; controls();
  };
  el("exam-submit").onclick = () => work(async () => {
    const s = session(), q = s.current_question;
    const requestKey = `speaking-request:${s.id}:${q.question_id}`;
    let requestId = sessionStorage.getItem(requestKey);
    if (!requestId) { requestId = crypto.randomUUID(); sessionStorage.setItem(requestKey, requestId); }
    let result;
    if (s.mode === "text") {
      if (!el("exam-text").value.trim()) throw new Error("Hãy nhập câu trả lời.");
      result = await api(endpoint("/text"), json({ question_id: q.question_id, request_id: requestId, version: s.version, text: el("exam-text").value }));
    } else {
      if (!blob || recordedQuestion !== q.question_id) throw new Error("Hãy ghi âm câu trả lời cho câu hỏi hiện tại.");
      const body = new FormData(); body.append("audio", blob, blob.name || (blob.type.includes("mp4") ? "answer.m4a" : "answer.webm"));
      body.append("question_id", q.question_id); body.append("request_id", requestId); body.append("version", s.version);
      body.append("vocabulary", el("exam-vocabulary").value.trim());
      body.append("pronunciation_consent", el("exam-pronunciation-consent").checked);
      result = await api(endpoint("/voice"), { method: "POST", body });
    }
    sessionStorage.removeItem(requestKey); releaseMic(); accept(result);
  });
  const reload = () => work(async () => { accept(await api(endpoint())); });
  el("exam-reload").onclick = reload;
  el("stale-reload").onclick = reload;
  el("use-voice").onclick = () => work(() => action("use_voice"));
  el("exam-export").onclick = () => work(async () => {
    const data = await api(endpoint("/export")), url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `speaking-exam-${session().id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  el("exam-grade").onclick = () => work(async () => {
    gradingProgress("Đang lấy hoặc chấm kết quả hai giám khảo…");
    el("checkpoint-status").textContent = "Đang chấm hai bản độc lập. Có thể mất 1–2 phút nếu phải chờ hạn mức token.";
    const result = await api(endpoint("/assessment"), { method: "POST" });
    el("checkpoint-status").textContent = result.retryable
      ? "Chưa chấm được lần này; chưa có kết quả nào được lưu. Hãy bấm chấm lại."
      : "Đã lưu hai bản chấm cho phiên này.";
    showGradingResult(result);
  });
  el("exam-regrade").onclick = () => {
    if (busy || !window.confirm("Chấm lại transcript đã lưu bằng hai giám khảo và loop hiện tại? Việc này gọi lại model và có thể tốn token. Nếu thành công, bản chấm và quyết định giáo viên cũ sẽ chuyển vào lịch sử.")) return;
    work(async () => {
      gradingProgress("Đang chấm lại bằng loop mới. Vui lòng chờ; không cần bấm lần nữa.");
      el("checkpoint-status").textContent = "Đang chấm lại transcript bằng loop mới…";
      let result;
      try { result = await api(endpoint("/assessment"), json({ force: true })); }
      catch (e) { gradingProgress(`Không hoàn tất chấm lại: ${e.message}. Kết quả cũ vẫn được giữ.`, true); throw e; }
      showGradingResult(result);
      el("checkpoint-status").textContent = result.regrade_failed ? result.message
        : result.retryable ? "Chưa chấm được lần này. Hãy thử lại sau."
        : "Đã lưu bản chấm mới. Bản chấm trước được giữ trong lịch sử.";
      if (result.regrade_failed && result.regrade_errors?.length) error(result.regrade_errors.join(" · "));
    });
  };
  el("session-save-audio").onchange = () => {
    const enabled = el("session-save-audio").checked;
    work(async () => {
      try { accept(await api(endpoint("/audio-preference"), json({ enabled, version: session().version }))); }
      catch (e) { el("session-save-audio").checked = Boolean(session().save_audio); throw e; }
    });
  };
  el("exam-weakness").onclick = () => work(async () => { renderWeakness(await api(endpoint("/weakness-profile"))); });
  el("teacher-action").onchange = () => { el("teacher-bands").hidden = el("teacher-action").value !== "edit"; };
  el("teacher-submit").onclick = () => work(async () => {
    const action = el("teacher-action").value, body = { teacher_id: el("teacher-id").value.trim(), action, note: el("teacher-note").value };
    if (action === "edit") {
      body.bands = {};
      for (const criterion of ["FC", "LR", "GRA", "PR"]) {
        const raw = el(`teacher-band-${criterion}`).value.trim();
        if (raw !== "") body.bands[criterion] = Number(raw);
      }
    }
    const result = await api(endpoint("/teacher-review"), json(body));
    session().assessment = result.assessment;
    renderAssessment(result.assessment);
    el("checkpoint-status").textContent = `Đã lưu quyết định của giáo viên (${action}).`;
  });
  function toSetup() {
    localStorage.removeItem("speaking-exam-session");
    snapshot = null; lastQuestion = null; clearAudio(); error();
    el("setup").hidden = false; el("exam-active").hidden = true;
    setupMode();
  }
  el("another-exam").onclick = toSetup;
  // Reachable at any point in a session, not only after the result card appears.
  el("exam-new").onclick = () => {
    const s = session();
    const unfinished = s && s.status !== "finished" && s.speaking_turns.length > 0;
    if (unfinished && !confirm("Bỏ phiên đang dở và bắt đầu phiên mới? Trang này sẽ không mở lại phiên cũ được.")) return;
    releaseMic(); toSetup();
  };
  window.addEventListener("beforeunload", (event) => { if (recorder?.state === "recording" || blob || el("exam-text").value.trim()) { event.preventDefault(); event.returnValue = ""; } });
  setInterval(tick, 200);
  work(async () => {
    const [cards, caps] = await Promise.all([api("/api/cue-cards"), api("/api/exam/capabilities")]);
    SpeakingFeedback.configure("exam-", caps.pronunciation);
    capability = caps; el("exam-capabilities").textContent = caps.limitations;
    setupMode();
    for (const card of cards.cards) { const option = document.createElement("option"); option.value = card.id; option.textContent = card.title; el("exam-topic").append(option); }
    const saved = localStorage.getItem("speaking-exam-session");
    if (saved) { try { accept(await api(`/api/exam/sessions/${saved}`)); } catch { error("Không tải được phiên đã lưu. Bạn có thể thử lại bằng cách tải lại trang hoặc bắt đầu phiên mới."); } }
  });
})();
