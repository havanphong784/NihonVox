"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const form = byId("chat-form");
  const input = byId("message-input");
  const send = byId("send-button");
  const clear = byId("clear-button");
  const replay = byId("replay-button");
  const healthButton = byId("health-button");
  const recordButton = byId("record-button");
  const recordStatus = byId("record-status");
  const recordTimer = byId("record-timer");
  const messages = byId("messages");
  const emptyState = byId("empty-state");
  const startButton = byId("start-practice");
  const learningSelects = { level: byId("level-select"), script: byId("script-select"), topic: byId("topic-select") };
  const learningKey = "japanese-voice-learning-v1";
  const defaults = { level: "N5", script: "hiragana", topic: "daily" };
  let activePractice = null;
  let pendingPermission = false;
  let busy = false;
  let composing = false;
  let lastAudio = null;
  let currentAudio = null;
  let recorder = null;
  let microphoneStream = null;
  let recordingStartedAt = 0;
  let recordingTimer = null;
  let recordingState = null;
  let permissionRequestId = 0;

  // Keep the requested default session; other API clients may choose their own IDs.
  let sessionId = "default";
  try {
    const saved = localStorage.getItem("japanese-voice-session");
    if (saved && /^[A-Za-z0-9_-]{1,64}$/.test(saved) && !/^practice-[a-f0-9]{32}$/.test(saved)) sessionId = saved;
    else localStorage.setItem("japanese-voice-session", sessionId);
  } catch (_) {
    // Private/restricted browsers still have a working session for this page.
  }

  const legacySessionId = sessionId;

  function loadLearningPreferences() {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(learningKey)); } catch (_) { /* Use defaults. */ }
    for (const [key, select] of Object.entries(learningSelects)) {
      select.value = Array.from(select.options).some(option => option.value === saved?.[key]) ? saved[key] : defaults[key];
      select.addEventListener("change", () => {
        try { localStorage.setItem(learningKey, JSON.stringify(readPreferences())); } catch (_) { /* Optional. */ }
      });
    }
  }

  function readPreferences() {
    return Object.fromEntries(Object.entries(learningSelects).map(([key, select]) => [key, select.value]));
  }

  function updatePracticeControls() {
    startButton.disabled = busy || pendingPermission || Boolean(recorder);
    for (const select of Object.values(learningSelects)) select.disabled = busy;
    send.disabled = busy || pendingPermission || Boolean(recorder);
  }

  function show(id, text = "") {
    const element = byId(id);
    element.textContent = text;
    element.hidden = !text;
  }

  function setBusy(value) {
    busy = value;
    clear.disabled = value;
    input.disabled = value;
    recordButton.disabled = value || pendingPermission || Boolean(recordingState?.stopping);
    updatePracticeControls();
    byId("processing").hidden = !value;
    form.setAttribute("aria-busy", String(value));
    if (!value) input.focus({ preventScroll: true });
  }

  async function request(url, options = {}, timeout = 180000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      let data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error("Server trả về dữ liệu không hợp lệ. Vui lòng thử lại.");
      }
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Server gặp lỗi. Vui lòng thử lại.");
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Hết thời gian chờ. Vui lòng thử lại.");
      if (error instanceof TypeError) throw new Error("Không kết nối được server. Hãy kiểm tra server đang chạy.");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
  }

  function appendMessage(role, text, source) {
    emptyState.hidden = true;
    const article = document.createElement("article");
    article.className = `message ${role}`;
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("span");
    name.textContent = role === "user" ? "Bạn" : "Trợ lý";
    meta.append(name);
    if (source) {
      const label = document.createElement("span");
      label.className = "source";
      label.textContent = source;
      meta.append(label);
    }
    const content = document.createElement("p");
    content.className = "message-text";
    content.textContent = text; // Never interpret learner/model text as HTML.
    if (role === "assistant") content.lang = "ja";
    article.append(meta, content);
    messages.append(article);
    scrollToLatest();
    return article;
  }

  function renderLearning(article, learning, fromVoice) {
    if (!learning || (!learning.correction && !learning.exercise)) return;
    function disclosure(title, className) {
      const details = document.createElement("details");
      details.className = className;
      const summary = document.createElement("summary");
      summary.textContent = title;
      details.append(summary);
      return details;
    }
    function paragraph(parent, text) {
      const element = document.createElement("p");
      element.textContent = text;
      parent.append(element);
    }
    const details = disclosure("Gợi ý học tập", "lesson-details");
    if (learning.correction) {
      paragraph(details, learning.correction);
      if (fromVoice) paragraph(details, "Góp ý dựa trên bản chép lời, không đánh giá phát âm.");
    }
    if (learning.exercise) {
      paragraph(details, learning.exercise.prompt);
      const answer = disclosure("Xem đáp án", "lesson-answer");
      paragraph(answer, learning.exercise.answer);
      details.append(answer);
    }
    article.append(details);
  }

  function renderReply(data, fromVoice = false) {
    lastAudio = null;
    replay.disabled = true;
    const article = appendMessage("assistant", data.reply, data.source);
    if (data.audio_url) attachAudio(article, data.audio_url);
    if (data.error_audio) {
      const note = document.createElement("p");
      note.className = "message-warning";
      note.textContent = data.error_audio;
      article.append(note);
    }
    renderLearning(article, data.learning, fromVoice);
    scrollToLatest();
  }

  function resetConversationView() {
    stopAudio();
    lastAudio = null;
    replay.disabled = true;
    messages.querySelectorAll(".message").forEach(message => message.remove());
    emptyState.hidden = false;
    input.value = "";
    show("audio-message");
    byId("latency").textContent = "Phản hồi gần nhất: —";
  }

  async function startPractice() {
    if (busy || pendingPermission || recorder) return;
    const preferences = readPreferences();
    const labels = Object.entries(learningSelects).map(([key, select]) =>
      Array.from(select.options).find(option => option.value === preferences[key])?.textContent.trim());
    const previous = activePractice ? sessionId : null;
    setBusy(true);
    startButton.textContent = "Đang mở buổi luyện…";
    show("error-message");
    try {
      const result = await request("/practice-sessions", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preferences),
      });
      if (!/^practice-[a-f0-9]{32}$/.test(result.session_id) || typeof result.reply !== "string" || !result.reply.trim()) {
        throw new Error("Không nhận được lời mở đầu hợp lệ. Vui lòng thử lại.");
      }
      resetConversationView();
      sessionId = result.session_id;
      activePractice = preferences;
      byId("active-practice").textContent = `Đang luyện: ${labels.join(" · ")}`;
      renderReply(result);
      if (previous && previous !== sessionId) {
        void request(`/sessions/${encodeURIComponent(previous)}`, { method: "DELETE" }, 5000).catch(() => {});
      }
    } catch (error) {
      show("error-message", error.message);
    } finally {
      startButton.textContent = "Bắt đầu luyện";
      setBusy(false);
    }
  }

  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    currentAudio = null;
  }

  async function playAudio(audio, autoplay = false) {
    if (currentAudio && currentAudio !== audio) stopAudio();
    currentAudio = audio;
    audio.currentTime = 0;
    try {
      await audio.play();
      show("audio-message");
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.name === "NotAllowedError" || autoplay) {
        show("audio-message", "Bấm “Phát” để nghe câu trả lời.");
      } else {
        show("audio-message", "Không phát được âm thanh. File có thể đã hết hạn; hãy gửi lại câu.");
      }
    }
  }

  function attachAudio(article, url) {
    // The server must only return our local UUID WAV route.
    if (!/^\/audio\/[a-f0-9]{32}\.wav$/.test(url)) {
      show("audio-message", "Đường dẫn âm thanh không hợp lệ.");
      return;
    }
    const audio = new Audio(url);
    audio.preload = "auto";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "play-button";
    button.textContent = "Phát";
    button.setAttribute("aria-label", "Phát câu trả lời tiếng Nhật");
    button.addEventListener("click", () => playAudio(audio));
    audio.addEventListener("play", () => { button.textContent = "Phát lại"; });
    audio.addEventListener("error", () => {
      show("audio-message", "Không tải được âm thanh. Bạn vẫn có thể đọc câu trả lời.");
    });
    article.append(button);
    lastAudio = audio;
    replay.disabled = false;
    scrollToLatest();
    void playAudio(audio, true);
  }

  function service(id, label, online) {
    const element = byId(id);
    element.dataset.state = online ? "good" : "bad";
    element.textContent = `${label}: ${online ? "Online" : "Offline"}`;
  }


  function setRecordStatus(text) {
    recordStatus.textContent = text;
  }

  function chooseRecordingType() {
    if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return null;
    return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((type) => MediaRecorder.isTypeSupported(type)) || null;
  }

  function recordingSuffix(mimeType) {
    if (mimeType.includes("ogg")) return ".ogg";
    if (mimeType.includes("mp4")) return ".mp4";
    return ".webm";
  }

  function updateRecordingTimer() {
    const seconds = Math.max(0, Math.floor((Date.now() - recordingStartedAt) / 1000));
    recordTimer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function releaseMicrophone() {
    if (microphoneStream) {
      microphoneStream.getTracks().forEach((track) => track.stop());
      microphoneStream = null;
    }
  }

  function resetRecordingUi(status = "録音待機中") {
    if (recordingTimer) clearInterval(recordingTimer);
    recordingTimer = null;
    recordingStartedAt = 0;
    recordTimer.textContent = "00:00";
    recorder = null;
    recordingState = null;
    recordButton.disabled = busy || pendingPermission;
    updatePracticeControls();
    recordButton.textContent = "Nói";
    recordButton.dataset.recording = "false";
    setRecordStatus(status);
  }

  async function submitRecording(blob, mimeType) {
    if (!blob || !blob.size) {
      resetRecordingUi("Không nhận được âm thanh. Hãy thử nói lại.");
      return;
    }
    setBusy(true);
    setRecordStatus("Đang nhận dạng...");
    const started = performance.now();
    try {
      const data = new FormData();
      data.append("audio", blob, `recording${recordingSuffix(mimeType)}`);
      data.append("session_id", sessionId);
      // Worst case: 120s STT + 90s Ollama + 60s VOICEVOX fallback/synthesis.
      const result = await request("/voice-chat", { method: "POST", body: data }, 300000);
      if (typeof result.transcript !== "string" || !result.transcript.trim() || typeof result.reply !== "string" || !result.reply.trim()) {
        throw new Error("Server trả về transcript hoặc câu trả lời rỗng. Vui lòng thử lại.");
      }
      stopAudio();
      replay.disabled = true;
      show("error-message");
      show("audio-message");
      appendMessage("user", result.transcript, "giọng nói");
      renderReply(result, true);
      setRecordStatus("録音待機中");
      scrollToLatest();
    } catch (error) {
      show("error-message", error.message);
      setRecordStatus("Có lỗi; bạn có thể thử lại hoặc nhập bằng bàn phím");
    } finally {
      byId("latency").textContent = `Phản hồi gần nhất: ${((performance.now() - started) / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} giây`;
      resetRecordingUi(recordStatus.textContent);
      setBusy(false);
    }
  }

  function stopRecording(discard = false) {
    if (recordingState && discard) recordingState.discard = true;
    if (!recorder) {
      releaseMicrophone();
      return;
    }
    if (recordingState.stopping) return;
    recordingState.stopping = true;
    recordButton.disabled = true;
    setRecordStatus(discard ? "Đang hủy ghi âm..." : "Đang chuẩn bị audio...");
    recorder.stop();
  }

  async function startRecording() {
    if (busy || pendingPermission || recorder) return;
    const mimeType = chooseRecordingType();
    if (!mimeType) {
      setRecordStatus("Trình duyệt này không hỗ trợ MediaRecorder audio");
      return;
    }
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      setRecordStatus("Không tìm thấy microphone trong trình duyệt");
      return;
    }
    const requestId = ++permissionRequestId;
    pendingPermission = true;
    updatePracticeControls();
    try {
      recordButton.disabled = true;
      setRecordStatus("Đang xin quyền microphone...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (requestId !== permissionRequestId) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      pendingPermission = false;
      const state = { stream, chunks: [], discard: false, stopping: false, recorder: null };
      microphoneStream = stream;
      const active = new MediaRecorder(stream, { mimeType });
      state.recorder = active;
      recordingState = state;
      recorder = active;
      updatePracticeControls();
      active.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) state.chunks.push(event.data);
      });
      active.addEventListener("error", () => {
        state.discard = true;
        state.stream.getTracks().forEach((track) => track.stop());
        if (recorder !== state.recorder) return;
        microphoneStream = null;
        recorder = null;
        recordingState = null;
        resetRecordingUi("Microphone gặp lỗi; hãy thử lại hoặc nhập bằng bàn phím");
      });
      active.addEventListener("stop", () => {
        const isCurrent = recorder === state.recorder;
        state.stream.getTracks().forEach((track) => track.stop());
        if (!isCurrent) return;
        microphoneStream = null;
        recorder = null;
        recordingState = null;
        const blob = new Blob(state.chunks, { type: mimeType });
        resetRecordingUi(state.discard ? "録音待機中" : "Đang tải audio...");
        if (!state.discard) void submitRecording(blob, mimeType);
      });
      active.start();
      recordingStartedAt = Date.now();
      recordingTimer = setInterval(updateRecordingTimer, 250);
      recordButton.disabled = false;
      recordButton.textContent = "Dừng";
      recordButton.dataset.recording = "true";
      setRecordStatus("Đang ghi âm...");
    } catch (error) {
      if (requestId !== permissionRequestId) return;
      pendingPermission = false;
      releaseMicrophone();
      resetRecordingUi(error.name === "NotAllowedError" ? "Không có quyền microphone; hãy cho phép trong trình duyệt" : "Không thể mở microphone; hãy kiểm tra thiết bị");
    }
  }

  async function checkHealth() {
    healthButton.disabled = true;
    const model = byId("model-status");
    try {
      const data = await request("/health", {}, 8000);
      service("ollama-status", "Ollama", data.ollama);
      service("voicevox-status", "VOICEVOX", data.voicevox);
      service("speech-status", "Whisper local", data.speech_model === true);
      model.dataset.state = data.model ? "good" : "bad";
      model.textContent = `Model: japanese-tutor${data.model ? "" : " (chưa sẵn sàng)"}`;
      const notes = [];
      if (!data.ollama) notes.push("Ollama đang offline; các câu theo rule vẫn hoạt động.");
      else if (!data.model) notes.push("Không tìm thấy model japanese-tutor trong Ollama.");
      if (!data.voicevox) notes.push("VOICEVOX đang offline; vẫn có thể trò chuyện bằng văn bản.");
      if (data.speech_model === false) notes.push("Whisper local chưa sẵn sàng; nút microphone sẽ không hoạt động.");
      show("health-message", notes.join(" "));
    } catch (error) {
      service("ollama-status", "Ollama", false);
      service("voicevox-status", "VOICEVOX", false);
      service("speech-status", "Whisper local", false);
      model.dataset.state = "bad";
      model.textContent = "Model: japanese-tutor (chưa kiểm tra được)";
      show("health-message", error.message);
    } finally {
      healthButton.disabled = false;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || composing || pendingPermission || recorder) return;
    const text = input.value.trim();
    show("error-message");
    if (!text) {
      show("error-message", "Vui lòng nhập câu trước khi gửi.");
      input.focus();
      return;
    }
    if (text.length > 2000) {
      show("error-message", "Câu quá dài. Vui lòng nhập tối đa 2000 ký tự.");
      return;
    }
    stopAudio();
    replay.disabled = true;
    show("audio-message");
    appendMessage("user", text);
    input.value = "";
    setBusy(true);
    const started = performance.now();
    try {
      const data = await request("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, session_id: sessionId }),
      });
      if (typeof data.reply !== "string" || !data.reply.trim()) {
        throw new Error("Server trả về câu trả lời rỗng. Vui lòng thử lại.");
      }
      renderReply(data);
    } catch (error) {
      show("error-message", error.message);
      input.value = text; // Preserve the learner's text for retry.
      replay.disabled = !lastAudio;
    } finally {
      byId("latency").textContent = `Phản hồi gần nhất: ${((performance.now() - started) / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} giây`;
      setBusy(false);
    }
  });

  input.addEventListener("compositionstart", () => { composing = true; });
  input.addEventListener("compositionend", () => { composing = false; });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  recordButton.addEventListener("click", () => {
    if (recorder) return stopRecording();
    return startRecording();
  });
  startButton.addEventListener("click", startPractice);
  replay.addEventListener("click", () => { if (lastAudio) void playAudio(lastAudio); });
  healthButton.addEventListener("click", checkHealth);
  clear.addEventListener("click", async () => {
    if (busy) return;
    permissionRequestId += 1;
    if (pendingPermission) {
      pendingPermission = false;
      resetRecordingUi();
    }
    if (recorder) stopRecording(true);
    setBusy(true);
    show("error-message");
    try {
      // Also forget the free-chat context we restore after clearing a lesson.
      if (activePractice && sessionId !== legacySessionId) {
        await request(`/sessions/${encodeURIComponent(legacySessionId)}`, { method: "DELETE" }, 15000);
      }
      await request(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }, 15000);
      resetConversationView();
      activePractice = null;
      sessionId = legacySessionId;
      byId("active-practice").textContent = "Chưa có buổi luyện. Bạn vẫn có thể nói hoặc gõ để trò chuyện tự do.";
    } catch (error) {
      show("error-message", error.message);
    } finally {
      setBusy(false);
    }
  });

  loadLearningPreferences();
  void checkHealth();
})();
