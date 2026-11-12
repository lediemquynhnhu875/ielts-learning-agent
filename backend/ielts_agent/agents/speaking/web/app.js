"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  topics: [], topic: 0, question: 0, part: 1, cueCards: [], cue: 0, configured: false, busy: false,
  requestingMic: false, recorder: null, stream: null, started: 0,
  timer: null, animation: null, context: null, analyser: null,
  drafts: new Map(), answers: [], sampleView: false, result: null,
  sessionId: crypto.randomUUID(), createdAt: new Date().toISOString(),
  preparation: { phase: "idle", seconds: 0, started: 0, timer: null },
  notes: new Map(), finishingRecording: false,
};
const audio = $("playback");
const canvas = $("waveform");
const icons = () => window.lucide?.createIcons();
const currentQuestion = () => state.part === 2 ? state.cueCards[state.cue] : state.topics[state.topic]?.questions[state.question];
const locked = () => state.busy || state.requestingMic || state.finishingRecording || state.preparation.phase === "preparing" || state.recorder?.state === "recording";
const clock = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

async function request(url, options) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Không đọc được phản hồi backend. Hãy thử lại sau."); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Yêu cầu chưa hợp lệ. Hãy thử lại.");
  return data;
}

function setError(message = "") {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function syncControls() {
  const isLocked = locked();
  const draft = state.drafts.get(currentQuestion()?.id);
  const isRecording = state.recorder?.state === "recording";
  $("record").disabled = state.busy || state.requestingMic || state.finishingRecording || !currentQuestion();
  $("record").classList.toggle("record-stop", isRecording);
  $("record").innerHTML = `<i data-lucide="${isRecording ? "square" : "mic"}"></i><span>${isRecording ? "Dừng ghi âm" : state.part === 2 ? "Bắt đầu nói" : "Bắt đầu ghi âm"}</span>`;
  document.querySelector(".recorder").classList.toggle("recording", isRecording);
  $("upload").disabled = isLocked;
  $("discard").disabled = isLocked;
  $("download-audio").disabled = isLocked || !audio.getAttribute("src");
  $("submit").disabled = isLocked || !draft || state.sampleView;
  $("submit").querySelector("span").textContent = state.busy ? "Đang xử lý…" : "Gửi câu trả lời";
  $("prev").disabled = isLocked || (state.part === 2 ? state.cue : state.question) === 0;
  $("next").disabled = isLocked || (state.part === 2 ? state.cue === state.cueCards.length - 1 : state.question === 4);
  $("shuffle-cue").disabled = isLocked || state.cueCards.length < 2;
  $("cue-select").disabled = isLocked;
  $("part-1").disabled = isLocked;
  $("part-2").disabled = isLocked || !state.cueCards.length;
  $("prep-notes").disabled = state.busy || state.requestingMic || state.finishingRecording || isRecording;
  $("prepare").disabled = state.busy || state.requestingMic || state.finishingRecording || isRecording;
  $("prepare").querySelector("span").textContent = state.preparation.phase === "preparing" ? "Hủy chuẩn bị" : "Chuẩn bị 1 phút";
  $("keep-fillers").disabled = isLocked;
  $("stt-vocabulary").disabled = isLocked;
  $("pronunciation-consent").disabled = isLocked || !state.pronunciationConfigured;
  $("sample-select").disabled = isLocked;
  $("sample-fillers").disabled = isLocked;
  $("load-sample").disabled = isLocked || !$("sample-select").value;
  $("reset").disabled = isLocked || (!state.answers.length && !state.drafts.size && !state.sampleView && !state.notes.size);
  $("export").disabled = isLocked || !state.answers.length;
  document.querySelectorAll(".topic-button").forEach((button) => { button.disabled = isLocked; });
  document.querySelectorAll(".history-actions button").forEach((button) => { button.disabled = isLocked; });
  icons();
}

function resetPreparation() {
  clearInterval(state.preparation.timer);
  state.preparation = { phase: "idle", seconds: 0, started: 0, timer: null };
  $("prep-timer").textContent = "01:00";
  $("speaking-timer").textContent = "02:00";
  $("prep-phase").classList.remove("active");
  $("speaking-phase").classList.remove("active");
  $("phase-progress").max = 60; $("phase-progress").value = 0;
  $("part2-status").textContent = "Sẵn sàng";
}

function finishPreparation() {
  if (state.preparation.phase !== "preparing") return;
  state.preparation.seconds = Math.min(60, (performance.now() - state.preparation.started) / 1000);
  clearInterval(state.preparation.timer);
  state.preparation.phase = "ready";
  $("prep-timer").textContent = clock(Math.ceil(60 - state.preparation.seconds));
  $("prep-phase").classList.remove("active");
}

async function acquireMicrophone() {
  if (!state.stream?.getAudioTracks().some((track) => track.readyState === "live")) {
    state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  }
  if (!state.context) state.context = new (window.AudioContext || window.webkitAudioContext)();
  await state.context.resume();
}

async function startPreparation() {
  if (state.preparation.phase === "preparing") {
    state.requestingMic = true; resetPreparation(); syncControls(); await cleanupMic(); state.requestingMic = false; $("record-status").textContent = "Sẵn sàng ghi âm"; syncControls(); return;
  }
  if (locked() || state.part !== 2) return;
  setError();
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setError("Trình duyệt chưa hỗ trợ ghi âm. Hãy mở bằng localhost/HTTPS hoặc chọn file audio."); return;
  }
  resetPreparation(); state.requestingMic = true; $("record-status").textContent = "Đang chờ quyền microphone"; syncControls();
  try {
    audio.pause(); await acquireMicrophone();
    state.stream.getAudioTracks().forEach((track) => { track.enabled = false; });
    state.requestingMic = false;
    state.preparation.phase = "preparing"; state.preparation.started = performance.now();
    $("prep-phase").classList.add("active"); $("part2-status").textContent = "Đang chuẩn bị"; $("record-status").textContent = "Chuẩn bị · chưa thu âm";
    state.preparation.timer = setInterval(() => {
      const elapsed = Math.min(60, (performance.now() - state.preparation.started) / 1000);
      $("prep-timer").textContent = clock(Math.ceil(60 - elapsed));
      $("phase-progress").value = elapsed;
      if (elapsed >= 60) { finishPreparation(); startRecording(); }
    }, 100);
    syncControls();
  } catch (error) {
    await cleanupMic(); state.requestingMic = false; resetPreparation();
    $("record-status").textContent = "Chưa ghi âm";
    setError(error.name === "NotAllowedError" ? "Chưa được cấp quyền microphone. Cho phép quyền mic hoặc chọn file audio." : "Không mở được microphone. Hãy kiểm tra thiết bị hoặc chọn file audio."); syncControls();
  }
}

function drawWave(samples = null) {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = state.recorder?.state === "recording" ? "#b9564b" : "#7ba997";
  const bars = Math.floor(rect.width / 5);
  for (let i = 0; i < bars; i++) {
    let amplitude = 0;
    if (samples) {
      const begin = Math.floor(i * samples.length / bars);
      const end = Math.floor((i + 1) * samples.length / bars);
      for (let j = begin; j < end; j++) amplitude = Math.max(amplitude, Math.abs(samples[j]));
    }
    const height = Math.max(2, Math.min(rect.height - 6, amplitude * rect.height * 2.5));
    ctx.fillRect(i * 5, (rect.height - height) / 2, 2, height);
  }
}

let previewSamples = null;
let waveformGeneration = 0;
async function previewWave(file) {
  const generation = ++waveformGeneration;
  try {
    const context = new (window.AudioContext || window.webkitAudioContext)();
    try {
      const decoded = await context.decodeAudioData(await file.arrayBuffer());
      if (generation === waveformGeneration) {
        previewSamples = decoded.getChannelData(0).slice();
        drawWave(previewSamples);
      }
    } finally { await context.close(); }
  } catch { if (generation === waveformGeneration) drawWave(); }
}
new ResizeObserver(() => drawWave(previewSamples)).observe(canvas);

function renderTopics() {
  $("topics").replaceChildren();
  state.topics.forEach((topic, index) => {
    const button = document.createElement("button");
    button.className = `topic-button${state.topic === index ? " active" : ""}`;
    button.setAttribute("aria-pressed", String(state.topic === index));
    button.innerHTML = `<i data-lucide="${topic.icon}"></i><span></span>`;
    button.querySelector("span").textContent = topic.name;
    button.addEventListener("click", () => { if (!locked()) { state.topic = index; state.question = 0; renderQuestion(); } });
    $("topics").append(button);
  });
}

function renderQuestion() {
  resetPreparation();
  state.sampleView = false;
  setError();
  const question = currentQuestion();
  const isPart2 = state.part === 2;
  const number = isPart2 ? state.cue : state.question;
  $("topic-name").textContent = isPart2 ? question.title : state.topics[state.topic].name;
  $("question").textContent = question.text;
  $("question-number").textContent = String(number + 1).padStart(2, "0");
  $("question-counter").textContent = `${String(number + 1).padStart(2, "0")} / ${String(isPart2 ? state.cueCards.length : 5).padStart(2, "0")}`;
  $("question-kind").textContent = isPart2 ? "CUE CARD" : "QUESTION";
  $("part-eyebrow").textContent = `IELTS SPEAKING · PART ${state.part}`;
  $("header-part").textContent = $("footer-part").textContent = `Part ${state.part}`;
  $("part-1").setAttribute("aria-selected", String(!isPart2));
  $("part-2").setAttribute("aria-selected", String(isPart2));
  $("topic-label").textContent = isPart2 ? "ĐỀ BÀI" : "CHỦ ĐỀ";
  $("topics").hidden = isPart2; $("cue-selector").hidden = !isPart2;
  $("cue-select").value = question.id;
  $("cue-content").hidden = $("part2-preparation").hidden = $("shuffle-cue").hidden = !isPart2;
  document.querySelector(".answer-section").classList.toggle("part2", isPart2);
  $("cue-points").replaceChildren();
  if (isPart2) {
    question.points.forEach((point) => { const li = document.createElement("li"); li.textContent = point; $("cue-points").append(li); });
    $("cue-explain").textContent = question.explain;
    $("prep-notes").value = state.notes.get(question.id) || "";
  }
  renderTopics();
  const draft = state.drafts.get(question.id);
  const previous = state.answers.findLast((answer) => answer.question.id === question.id);
  audio.pause();
  audio.src = draft?.url || previous?.audioUrl || "";
  $("recording-preview").hidden = !draft && !previous;
  $("audio-name").textContent = draft?.name || "Bản thu đã gửi";
  $("discard").hidden = !draft;
  $("record-status").textContent = draft ? "Bản thu sẵn sàng" : "Sẵn sàng ghi âm";
  $("timer").textContent = "00:00";
  waveformGeneration++;
  previewSamples = null;
  drawWave();
  if (draft) previewWave(draft.file);
  renderResult(previous || null);
  syncControls();
}

function setDraft(file, preparation = null) {
  state.sampleView = false;
  const question = currentQuestion();
  const previous = state.drafts.get(question.id);
  if (previous && !state.answers.some((answer) => answer.audioUrl === previous.url)) URL.revokeObjectURL(previous.url);
  const draft = { file, url: URL.createObjectURL(file), name: file.name,
    preparation: state.part === 2 ? (preparation || { seconds: 0, notes: state.notes.get(question.id) || "", limit_seconds: 60 }) : null };
  state.drafts.set(question.id, draft);
  audio.src = draft.url;
  $("recording-preview").hidden = false;
  $("discard").hidden = false;
  $("audio-name").textContent = draft.name;
  $("record-status").textContent = "Bản thu sẵn sàng";
  renderResult(null);
  previewWave(file);
  syncControls();
}

async function cleanupMic() {
  clearInterval(state.timer);
  cancelAnimationFrame(state.animation);
  state.stream?.getTracks().forEach((track) => track.stop());
  state.stream = null;
  if (state.context) { await state.context.close().catch(() => {}); state.context = null; }
  state.analyser = null;
}

async function startRecording() {
  if (state.recorder?.state === "recording") { state.recorder.stop(); return; }
  if (state.part === 2 && state.preparation.phase === "completed") resetPreparation();
  if (state.part === 2 && state.preparation.phase === "preparing") finishPreparation();
  if (locked()) return;
  setError();
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setError("Trình duyệt chưa hỗ trợ ghi âm. Hãy mở bằng localhost/HTTPS hoặc chọn file audio.");
    return;
  }
  state.requestingMic = true;
  $("record-status").textContent = "Đang chờ quyền microphone";
  syncControls();
  try {
    audio.pause();
    await acquireMicrophone();
    state.stream.getAudioTracks().forEach((track) => { track.enabled = true; });
    const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type));
    state.recorder = new MediaRecorder(state.stream, mime ? { mimeType: mime } : {});
    const chunks = [];
    const recordingQuestion = currentQuestion();
    const preparation = state.part === 2 ? { seconds: Math.round(state.preparation.seconds * 1000) / 1000,
      notes: state.notes.get(recordingQuestion.id) || "", limit_seconds: 60 } : null;
    state.recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
    state.recorder.addEventListener("stop", async () => {
      state.finishingRecording = true; syncControls();
      const type = state.recorder.mimeType || mime || "audio/webm";
      const extension = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const file = new File(chunks, `answer-${recordingQuestion.id}.${extension}`, { type });
      await cleanupMic();
      state.finishingRecording = false;
      if (state.part === 2) { state.preparation.phase = "completed"; $("speaking-phase").classList.remove("active"); $("part2-status").textContent = "Đã thu âm"; }
      setDraft(file, preparation);
    }, { once: true });
    state.recorder.addEventListener("error", async () => { await cleanupMic(); setError("Ghi âm bị gián đoạn. Hãy thu lại."); syncControls(); });
    waveformGeneration++;
    previewSamples = null;
    const input = state.context.createMediaStreamSource(state.stream);
    state.analyser = state.context.createAnalyser();
    state.analyser.fftSize = 2048;
    input.connect(state.analyser);
    const data = new Float32Array(state.analyser.fftSize);
    const animate = () => { if (!state.analyser) return; state.analyser.getFloatTimeDomainData(data); drawWave(data); state.animation = requestAnimationFrame(animate); };
    state.recorder.start(250);
    state.started = performance.now();
    state.requestingMic = false;
    $("record-status").textContent = "Đang ghi âm";
    $("timer").textContent = state.part === 2 ? "02:00" : "00:00";
    if (state.part === 2) {
      state.preparation.phase = "recording"; $("part2-status").textContent = "Đang nói";
      $("speaking-phase").classList.add("active"); $("phase-progress").max = 120; $("phase-progress").value = 0;
    }
    state.timer = setInterval(() => {
      const elapsed = (performance.now() - state.started) / 1000;
      const limit = preparation ? 120 : 180;
      $("timer").textContent = preparation ? clock(Math.ceil(Math.max(0, limit - elapsed))) : clock(elapsed);
      if (preparation) { $("speaking-timer").textContent = $("timer").textContent; $("phase-progress").value = Math.min(limit, elapsed); }
      if (elapsed >= limit && state.recorder.state === "recording") state.recorder.stop();
    }, 100);
    animate();
    syncControls();
  } catch (error) {
    await cleanupMic();
    state.requestingMic = false;
    state.recorder = null;
    if (state.part === 2) { state.preparation.phase = "ready"; $("part2-status").textContent = "Chưa ghi âm"; }
    $("record-status").textContent = "Chưa ghi âm";
    setError(error.name === "NotAllowedError" ? "Chưa được cấp quyền microphone. Cho phép quyền mic hoặc chọn file audio." : "Không mở được microphone. Hãy kiểm tra thiết bị hoặc chọn file audio.");
    syncControls();
  }
}

function renderResult(result) {
  state.result = result;
  $("result-empty").hidden = Boolean(result);
  $("result-content").hidden = !result;
  $("result-tag").className = "tag";
  if (!result) { $("result-tag").textContent = "Chưa có kết quả"; return; }
  SpeakingFeedback.render($("pronunciation-result"), result.pronunciation);
  const valid = result.quality.timing_valid;
  const review = result.quality.status !== "ok";
  $("result-tag").textContent = review ? "Cần kiểm tra" : "Đã nhận transcript";
  $("result-tag").classList.add(review ? "review" : "ready");
  $("result-source").textContent = result.source === "benchmark" ? `Kết quả đã lưu · ${result.sample}` : `Câu trả lời · ${result.question.id}`;
  $("latency").textContent = `${result.processing_seconds.toFixed(2)} s · STT`;
  $("quality-warnings").replaceChildren();
  result.quality.issues.forEach((issue) => { const element = document.createElement("div"); element.className = "notice"; element.textContent = issue.message; $("quality-warnings").append(element); });
  $("transcript").replaceChildren();
  if (valid) {
    result.words.forEach((word) => {
      const button = document.createElement("button");
      button.className = "word";
      button.textContent = `${word.word} `;
      button.title = `${word.start.toFixed(2)}–${word.end.toFixed(2)} s`;
      button.setAttribute("aria-label", `${word.word}, ${word.start.toFixed(2)} giây`);
      button.addEventListener("click", () => { audio.currentTime = word.start; audio.play().catch(() => {}); });
      $("transcript").append(button);
    });
  } else { $("transcript").textContent = result.transcript || "Không có transcript."; }
  const timing = result.metrics.timing;
  const vad = result.metrics.audio_timing?.status === "ok" ? result.metrics.audio_timing : null;
  const candidates = result.metrics.disfluency_candidates;
  const repeatedPhrases = Array.isArray(candidates?.repeated_phrases) ? candidates.repeated_phrases : null;
  const repairCandidates = Array.isArray(candidates?.repair_candidates) ? candidates.repair_candidates : null;
  const entries = [
    ["Số từ nhận dạng", result.metrics.word_count],
    ["Từ / phút · cửa sổ VAD", vad?.words_per_minute],
    ["Khoảng không nói · VAD", vad?.internal_pause_count],
    ["Filler nhận dạng", result.metrics.filler_count],
    ["Lặp từ liền nhau", Array.isArray(result.metrics.adjacent_repetitions) ? result.metrics.adjacent_repetitions.length : null],
    ["Lặp cụm nhận dạng", repeatedPhrases?.length ?? null],
    ["Dấu hiệu tự sửa", repairCandidates?.length ?? null],
    ["Tổng khoảng không nói", vad ? `${vad.pause_seconds} s` : null],
    ["Khoảng không nói dài nhất", vad ? `${vad.longest_pause_seconds} s` : null],
  ];
  $("metrics").replaceChildren();
  for (const [label, value] of entries) {
    const item = document.createElement("div"); item.className = "metric";
    const caption = document.createElement("span"); caption.textContent = label;
    const number = document.createElement("strong"); number.textContent = value == null ? "—" : value;
    number.classList.toggle("unavailable", value == null);
    item.append(caption, number); $("metrics").append(item);
  }
  $("comparison").replaceChildren();
  for (const [source, values] of [
    ["VAD · audio", [vad?.words_per_minute, vad?.internal_pause_count, vad?.pause_seconds, vad?.speech_window_seconds]],
    ["STT · timestamps", [timing?.words_per_minute, timing?.pause_count, timing?.pause_seconds, timing?.speech_seconds]],
  ]) {
    const row = document.createElement("tr"); if (source.startsWith("STT")) row.className = "stt-comparison";
    const label = document.createElement("td"); label.textContent = source; row.append(label);
    values.forEach((value, index) => {
      const cell = document.createElement("td"); cell.textContent = value == null ? "—" : index >= 2 ? `${value} s` : value;
      if (value == null) cell.classList.add("unavailable"); row.append(cell);
    });
    $("comparison").append(row);
  }
  $("vad-pauses").replaceChildren();
  for (const pause of vad?.pauses || []) {
    const row = document.createElement("tr");
    for (const value of [pause.start, pause.end, pause.seconds]) { const cell = document.createElement("td"); cell.textContent = `${value.toFixed(3)} s`; row.append(cell); }
    $("vad-pauses").append(row);
  }
  $("vad-details").hidden = !vad;
  $("disfluency-list").replaceChildren();
  for (const phrase of repeatedPhrases || []) { const li = document.createElement("li"); li.textContent = `“${phrase.text}” · lặp ${phrase.count} lần`; $("disfluency-list").append(li); }
  for (const repair of repairCandidates || []) { const li = document.createElement("li"); li.textContent = `“${repair.marker}” · ${repair.type === "restarted_connector" ? "từ nối được dùng lại" : "dấu hiệu đổi ý"} · cần nghe lại`; $("disfluency-list").append(li); }
  $("disfluency-details").hidden = !(repeatedPhrases?.length || repairCandidates?.length);
  const flagged = new Set(result.quality.issues.flatMap((issue) => issue.word_indices));
  $("words").replaceChildren();
  result.words.forEach((word, index) => {
    const tr = document.createElement("tr"); if (flagged.has(index)) tr.className = "flagged";
    for (const value of [word.word, word.start, word.end]) { const td = document.createElement("td"); td.textContent = typeof value === "number" ? `${value.toFixed(2)} s` : value; tr.append(td); }
    $("words").append(tr);
  });
  $("timestamps-details").hidden = !result.words.length;
}

audio.addEventListener("timeupdate", () => {
  if (!state.result?.quality.timing_valid) return;
  $("transcript").querySelectorAll(".word").forEach((button, index) => {
    const word = state.result.words[index];
    button.classList.toggle("current", audio.currentTime >= word.start && audio.currentTime < word.end);
  });
});

function renderHistory() {
  $("session-count").textContent = state.answers.length;
  $("history-count").textContent = `${state.answers.length} câu`;
  $("history-empty").hidden = Boolean(state.answers.length);
  $("history-table-wrap").hidden = !state.answers.length;
  $("history").replaceChildren();
  state.answers.toReversed().forEach((answer) => {
    const tr = document.createElement("tr");
    const question = document.createElement("td"); question.textContent = `Part ${answer.part || answer.question.part || 1} · ${answer.question.text}`;
    const duration = document.createElement("td"); duration.textContent = `${answer.audio_seconds.toFixed(1)} s`;
    const quality = document.createElement("td"); quality.className = `history-status${answer.quality.status === "ok" ? "" : " review"}`; quality.textContent = answer.quality.status === "ok" ? "Có metrics" : "Cần kiểm tra";
    const actions = document.createElement("td"); const group = document.createElement("div"); group.className = "history-actions";
    const view = document.createElement("button"); view.className = "icon-button"; view.title = "Xem câu trả lời"; view.setAttribute("aria-label", `Xem câu trả lời ${answer.question.id}`); view.innerHTML = '<i data-lucide="arrow-up-right"></i>';
    view.addEventListener("click", () => {
      if (locked()) return;
      state.part = answer.part || answer.question.part || 1;
      if (state.part === 2) state.cue = state.cueCards.findIndex((card) => card.id === answer.question.id);
      else {
        state.topic = state.topics.findIndex((topic) => topic.questions.some((q) => q.id === answer.question.id));
        state.question = state.topics[state.topic].questions.findIndex((q) => q.id === answer.question.id);
      }
      renderQuestion(); state.sampleView = true; audio.src = answer.audioUrl; $("recording-preview").hidden = false; $("discard").hidden = true; $("audio-name").textContent = "Bản thu đã gửi"; $("record-status").textContent = "Đang xem câu trả lời đã gửi"; renderResult(answer); syncControls();
    });
    group.append(view); actions.append(group); tr.append(question, duration, quality, actions); $("history").append(tr);
  });
  syncControls();
}

$("record").addEventListener("click", startRecording);
$("prepare").addEventListener("click", startPreparation);
$("prep-notes").addEventListener("input", () => {
  const text = $("prep-notes").value;
  if (text) state.notes.set(currentQuestion().id, text); else state.notes.delete(currentQuestion().id);
  syncControls();
});
for (const part of [1, 2]) $("part-" + part).addEventListener("click", () => {
  if (!locked()) { state.part = part; renderQuestion(); }
});
$("cue-select").addEventListener("change", () => { if (!locked()) { state.cue = state.cueCards.findIndex((card) => card.id === $("cue-select").value); renderQuestion(); } });
$("shuffle-cue").addEventListener("click", () => {
  if (!locked()) { state.cue = (state.cue + 1 + Math.floor(Math.random() * (state.cueCards.length - 1))) % state.cueCards.length; renderQuestion(); }
});
$("upload").addEventListener("click", () => $("audio-file").click());
$("audio-file").addEventListener("change", () => {
  const file = $("audio-file").files[0];
  $("audio-file").value = "";
  if (!file || locked()) return;
  if (file.size > 24 * 1024 * 1024) { setError("File quá lớn. Giới hạn audio là 24 MB."); return; }
  setError(); setDraft(file);
});
$("discard").addEventListener("click", () => {
  const draft = state.drafts.get(currentQuestion().id);
  if (draft && !state.answers.some((answer) => answer.audioUrl === draft.url)) URL.revokeObjectURL(draft.url);
  state.drafts.delete(currentQuestion().id); renderQuestion();
});
$("prev").addEventListener("click", () => {
  if (locked()) return;
  if (state.part === 2 && state.cue > 0) state.cue--; else if (state.part === 1 && state.question > 0) state.question--;
  renderQuestion();
});
$("next").addEventListener("click", () => {
  if (locked()) return;
  if (state.part === 2 && state.cue < state.cueCards.length - 1) state.cue++; else if (state.part === 1 && state.question < 4) state.question++;
  renderQuestion();
});
$("submit").addEventListener("click", async () => {
  const draft = state.drafts.get(currentQuestion().id);
  if (!draft || locked() || state.sampleView) return;
  state.busy = true; setError(); syncControls();
  const form = new FormData(); form.append("audio", draft.file); form.append("question_id", currentQuestion().id); form.append("keep_fillers", $("keep-fillers").checked);
  form.append("vocabulary", $("stt-vocabulary").value.trim());
  form.append("pronunciation_consent", $("pronunciation-consent").checked);
  if (draft.preparation) { form.append("preparation_seconds", draft.preparation.seconds); form.append("notes", draft.preparation.notes); }
  try {
    const result = await request("/api/transcribe", { method: "POST", body: form });
    const answer = { ...result, id: crypto.randomUUID(), submittedAt: new Date().toISOString(), audioUrl: draft.url, audio_filename: draft.file.name };
    state.answers.push(answer); state.drafts.delete(currentQuestion().id);
    $("discard").hidden = true; $("audio-name").textContent = "Bản thu đã gửi";
    renderResult(answer); renderHistory();
  } catch (error) { setError(error.message || "Không gửi được audio. Bản thu vẫn còn để gửi lại."); }
  finally { state.busy = false; syncControls(); }
});
$("load-sample").addEventListener("click", async () => {
  if (locked()) return;
  state.busy = true; setError(); syncControls();
  try {
    const sample = $("sample-select").value;
    const result = await request(`/api/samples/${encodeURIComponent(sample)}?keep_fillers=${$("sample-fillers").checked}`);
    const audioUrl = `/api/samples/${encodeURIComponent(sample)}/audio`;
    state.sampleView = true; audio.src = audioUrl;
    $("recording-preview").hidden = false; $("discard").hidden = true; $("audio-name").textContent = `Audio mẫu · ${sample}`;
    $("record-status").textContent = "Đang xem mẫu đã lưu";
    renderResult(result);
    previewSamples = null; waveformGeneration++; drawWave();
    fetch(audioUrl).then((response) => response.blob()).then((blob) => {
      if (state.sampleView && state.result === result && !locked()) previewWave(blob);
    }).catch(() => {});
  } catch (error) { setError(error.message); }
  finally { state.busy = false; syncControls(); }
});
$("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(state.result.transcript); $("copy").title = "Đã sao chép"; }
  catch { setError("Không truy cập được clipboard. Bạn có thể chọn transcript trực tiếp."); }
});
$("download-audio").addEventListener("click", async () => {
  const source = audio.getAttribute("src");
  if (!source || locked()) return;
  const answer = state.answers.findLast((item) => item.audioUrl === source);
  const draft = state.drafts.get(currentQuestion().id);
  const name = answer ? `${answer.question.id}-${answer.id.slice(0, 8)}`
    : state.sampleView && state.result?.sample ? state.result.sample
    : draft?.name.replace(/\.[^.]+$/, "") || currentQuestion().id;
  $("download-audio").disabled = true;
  try {
    const response = await fetch(source);
    if (!response.ok) throw new Error("Không đọc được audio.");
    const blob = await response.blob();
    const mime = blob.type.split(";")[0].toLowerCase();
    const extension = { "audio/webm": "webm", "video/webm": "webm", "audio/mp4": "m4a", "audio/x-m4a": "m4a",
      "video/mp4": "mp4", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/wav": "wav",
      "audio/x-wav": "wav", "audio/flac": "flac", "audio/x-flac": "flac" }[mime]
      || (answer?.audio_filename || (draft?.url === source ? draft.file.name : "answer.webm")).split(".").at(-1);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = `${name}.${extension}`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch { setError("Không tải được audio. Giữ trang đang mở và thử lại."); }
  finally { syncControls(); }
});
$("export").addEventListener("click", async () => {
  const parts = [...new Set(state.answers.map((answer) => answer.part || answer.question.part || 1))].sort();
  const data = { schema_version: "1.2", session_id: state.sessionId, created_at: state.createdAt,
    exported_at: new Date().toISOString(), part: parts.length === 1 ? parts[0] : null, parts,
    answers: state.answers.map(({ audioUrl, ...answer }) => answer) };
  state.busy = true; syncControls();
  try {
    const exported = await request("/api/speaking/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `speaking-session-${state.sessionId.slice(0, 8)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { setError(error.message); }
  finally { state.busy = false; syncControls(); }
});
$("reset").addEventListener("click", () => $("reset-dialog").showModal());
$("reset-cancel").addEventListener("click", () => $("reset-dialog").close());
$("reset-confirm").addEventListener("click", () => {
  const urls = new Set([...state.drafts.values()].map((draft) => draft.url).concat(state.answers.map((answer) => answer.audioUrl)));
  urls.forEach((url) => URL.revokeObjectURL(url));
  state.drafts.clear(); state.answers = []; state.notes.clear(); state.sessionId = crypto.randomUUID(); state.createdAt = new Date().toISOString(); state.topic = 0; state.question = 0; state.cue = 0;
  $("reset-dialog").close(); renderQuestion(); renderHistory();
});
window.addEventListener("beforeunload", (event) => { if (state.answers.length || state.drafts.size || state.notes.size || locked()) { event.preventDefault(); event.returnValue = ""; } });

async function init() {
  try {
    const [health, questions, samples, cues] = await Promise.all([request("/api/health"), request("/api/questions"), request("/api/samples"), request("/api/cue-cards")]);
    state.pronunciationConfigured = Boolean(health.pronunciation?.configured);
    SpeakingFeedback.configure("", health.pronunciation);
    state.configured = health.groq_configured; state.topics = questions.topics; state.cueCards = cues.cards;
    $("footer-model").textContent = health.model;
    $("connection").classList.toggle("offline", !state.configured);
    $("connection").querySelector("span:last-child").textContent = state.configured ? "Groq sẵn sàng" : "Chưa có API key";
    $("config-warning").hidden = state.configured;
    $("config-warning").textContent = "Backend chưa có Groq API key. Các mẫu đã lưu vẫn có thể mở để kiểm tra.";
    for (const name of samples.samples) { const option = document.createElement("option"); option.value = name; option.textContent = name; $("sample-select").append(option); }
    for (const card of state.cueCards) { const option = document.createElement("option"); option.value = card.id; option.textContent = card.title; $("cue-select").append(option); }
    renderQuestion(); renderHistory();
  } catch { setError("Không kết nối được backend. Hãy tải lại trang sau khi server sẵn sàng."); $("connection").querySelector("span:last-child").textContent = "Mất kết nối"; $("connection").classList.add("offline"); syncControls(); }
}
icons(); init();
