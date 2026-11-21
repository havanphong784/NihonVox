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
  const quickLessonSelect = byId("quick-lesson-select");
  const quickStartButton = byId("start-quick-lesson");
  const practiceGoal = byId("practice-goal");
  const translationToggle = byId("translation-toggle");
  const translationStatus = byId("translation-status");
  const transcriptActions = byId("transcript-actions");
  const transcriptNote = byId("transcript-note");
  const cancelTranscript = byId("cancel-transcript");
  const rerecordTranscript = byId("rerecord-transcript");
  const learningSelects = { level: byId("level-select"), script: byId("script-select"), topic: byId("topic-select") };
  const learningKey = "japanese-voice-learning-v1";
  const defaults = { level: "N5", script: "hiragana", topic: "daily" };
  let activePractice = null;
  let pendingPermission = false;
  let transcriptOrigin = null;
  let transcriptGeneration = 0;
  let serverTranslationEnabled = true;
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

  function loadTranslationPreference() {
    let saved = false;
    try { saved = localStorage.getItem("japanese-voice-translation-v1") === "true"; } catch (_) { /* Optional. */ }
    translationToggle.checked = saved;
    translationToggle.addEventListener("change", () => {
      try { localStorage.setItem("japanese-voice-translation-v1", String(translationToggle.checked)); } catch (_) { /* Optional. */ }
      updateTranslationStatus();
    });
    updateTranslationStatus();
  }

  function updateTranslationStatus() {
    if (!serverTranslationEnabled) {
      translationToggle.checked = false;
      translationToggle.disabled = true;
      translationStatus.textContent = "Dịch đang tắt trên máy chủ.";
      return;
    }
    translationToggle.disabled = false;
    translationStatus.textContent = translationToggle.checked
      ? "Chỉ lời đáp AI được gửi tới Google Translate."
      : "Dịch đang tắt; hội thoại vẫn chạy local. ";
  }

  async function loadLessons() {
    quickLessonSelect.value = quickLessonSelect.value || "order-food";
    try {
      const data = await request("/lessons", {}, 10000);
      if (!Array.isArray(data.lessons) || !data.lessons.length) return;
      quickLessonSelect.replaceChildren(...data.lessons.map(lesson => {
        const option = document.createElement("option");
        option.value = lesson.id;
        option.textContent = `${lesson.label} · ${lesson.level}`;
        option.dataset.goal = lesson.goal || "";
        return option;
      }));
      quickLessonSelect.value = data.lessons.some(lesson => lesson.id === "order-food") ? "order-food" : data.lessons[0].id;
    } catch (_) {
      // The three static options remain usable if the metadata request fails.
    }
  }

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

  function lessonComplete() {
    return activePractice?.mode === "quick" && activePractice.progress?.completed === true;
  }

  function updatePracticeControls() {
    const blocked = busy || pendingPermission || Boolean(recorder);
    startButton.disabled = blocked;
    quickStartButton.disabled = blocked;
    for (const select of Object.values(learningSelects)) select.disabled = busy;
    quickLessonSelect.disabled = busy;
    send.disabled = blocked || lessonComplete();
    recordButton.disabled = blocked || lessonComplete();
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

  function renderProgress(progress) {
    if (!progress || !activePractice || activePractice.mode !== "quick") return;
    activePractice.progress = progress;
    const selected = Array.from(quickLessonSelect.options).find(option => option.value === progress.lesson_id);
    const label = selected?.textContent?.split(" · ")[0] || progress.lesson_id;
    byId("active-practice").textContent = `${progress.completed ? "Hoàn thành" : "Đang luyện"}: ${label} · ${progress.completed_turns}/${progress.total_turns} lượt`;
    if (progress.completed && progress.practice_sentence) {
      practiceGoal.hidden = false;
      practiceGoal.textContent = `Câu nên luyện lại: ${progress.practice_sentence.japanese} · ${progress.practice_sentence.vietnamese}`;
    } else {
      practiceGoal.hidden = true;
      practiceGoal.textContent = "";
    }
    updatePracticeControls();
  }

  function clearTranscriptDraft() {
    transcriptGeneration += 1;
    transcriptOrigin = null;
    transcriptActions.hidden = true;
    transcriptNote.textContent = "Đây là bản chép lời từ microphone. Hãy sửa trước khi gửi.";
  }

  function renderReply(data, fromVoice = false) {
    if (data.progress) renderProgress(data.progress);
    lastAudio = null;
    replay.disabled = true;
    const article = appendMessage("assistant", data.reply, data.source);
    if (typeof data.translation === "string" && data.translation.trim()) {
      const translated = document.createElement("p");
      translated.className = "message-translation";
      translated.lang = "vi";
      translated.textContent = data.translation;
      const label = document.createElement("p");
      label.className = "translation-label";
      label.textContent = "Bản dịch Google · Tiếng Việt";
      article.append(translated, label);
    } else if (data.error_translation) {
      const notice = document.createElement("p");
      notice.className = "translation-notice";
      notice.textContent = data.error_translation;
      article.append(notice);
    }
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
    clearTranscriptDraft();
    practiceGoal.hidden = true;
    practiceGoal.textContent = "";
    show("audio-message");
    byId("latency").textContent = "Phản hồi gần nhất: —";
  }

  async function openPractice(payload, mode, description) {
    if (busy || pendingPermission || recorder) return;
    const previous = activePractice ? sessionId : null;
    setBusy(true);
    startButton.textContent = mode === "quick" ? "Đang mở bài nhanh…" : "Đang mở buổi luyện…";
    quickStartButton.textContent = mode === "quick" ? "Đang mở bài nhanh…" : "Bắt đầu bài nhanh";
    show("error-message");
    try {
      const result = await request("/practice-sessions", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (!/^practice-[a-f0-9]{32}$/.test(result.session_id) || typeof result.reply !== "string" || !result.reply.trim()) {
        throw new Error("Không nhận được lời mở đầu hợp lệ. Vui lòng thử lại.");
      }
      resetConversationView();
      sessionId = result.session_id;
      activePractice = { mode, progress: result.progress || null };
      byId("active-practice").textContent = description;
      renderReply(result);
      if (previous && previous !== sessionId) {
        void request(`/sessions/${encodeURIComponent(previous)}`, { method: "DELETE" }, 5000).catch(() => {});
      }
    } catch (error) {
      show("error-message", error.message);
    } finally {
      startButton.textContent = "Bắt đầu luyện";
      quickStartButton.textContent = "Bắt đầu bài nhanh";
      setBusy(false);
    }
  }

  async function startPractice() {
    const preferences = readPreferences();
    const labels = Object.entries(learningSelects).map(([key, select]) =>
      Array.from(select.options).find(option => option.value === preferences[key])?.textContent.trim());
    await openPractice({ ...preferences, translate: translationToggle.checked }, "custom", `Đang luyện: ${labels.join(" · ")}`);
  }

  async function startQuickLesson() {
    const option = Array.from(quickLessonSelect.options).find(item => item.value === quickLessonSelect.value);
    await openPractice({ lesson_id: quickLessonSelect.value, translate: translationToggle.checked }, "quick",
      `Đang luyện nhanh: ${option?.textContent || quickLessonSelect.value}`);
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
      resetRecordingUi("Không nhận được âm thanh. Hãy thử lại.");
      return;
    }
    setBusy(true);
    setRecordStatus("Đang nhận dạng...");
    const started = performance.now();
    const generation = ++transcriptGeneration;
    try {
      const data = new FormData();
      data.append("audio", blob, `recording${recordingSuffix(mimeType)}`);
      const result = await request("/transcribe", { method: "POST", body: data }, 300000);
      if (generation !== transcriptGeneration) return;
      if (typeof result.transcript !== "string" || !result.transcript.trim()) {
        throw new Error("Server trả về bản chép lời rỗng. Vui lòng thử lại.");
      }
      input.value = result.transcript.trim();
      transcriptOrigin = "voice";
      transcriptActions.hidden = false;
      transcriptNote.textContent = "Đây là bản chép lời từ microphone. Hãy sửa trước khi gửi.";
      input.focus({ preventScroll: true });
      show("error-message");
      setRecordStatus("Đã nhận dạng; kiểm tra rồi bấm Gửi");
      scrollToLatest();
    } catch (error) {
      if (generation === transcriptGeneration) {
        show("error-message", error.message);
        setRecordStatus("Có lỗi; bạn có thể thử lại hoặc nhập bằng bàn phím");
      }
    } finally {
      if (generation === transcriptGeneration) {
        byId("latency").textContent = `Nhận dạng: ${((performance.now() - started) / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} giây`;
        resetRecordingUi(recordStatus.textContent);
        setBusy(false);
      }
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
    if (busy || pendingPermission || recorder || lessonComplete()) return;
    if (input.value.trim() && !transcriptOrigin) {
      setRecordStatus("Bạn đang có bản nháp; hãy gửi hoặc xóa trước khi nói");
      return;
    }
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
      serverTranslationEnabled = data.translation_enabled !== false;
      updateTranslationStatus();
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
      serverTranslationEnabled = false;
      updateTranslationStatus();
      model.dataset.state = "bad";
      model.textContent = "Model: japanese-tutor (chưa kiểm tra được)";
      show("health-message", error.message);
    } finally {
      healthButton.disabled = false;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || composing || pendingPermission || recorder || lessonComplete()) return;
    const text = input.value.trim();
    const origin = transcriptOrigin;
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
    setBusy(true);
    const started = performance.now();
    try {
      const data = await request("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, session_id: sessionId, translate: translationToggle.checked }),
      });
      if (typeof data.reply !== "string" || !data.reply.trim()) {
        throw new Error("Server trả về câu trả lời rỗng. Vui lòng thử lại.");
      }
      appendMessage("user", text, origin === "voice" ? "giọng nói" : undefined);
      input.value = "";
      clearTranscriptDraft();
      renderReply(data, origin === "voice");
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
  quickStartButton.addEventListener("click", startQuickLesson);
  cancelTranscript.addEventListener("click", () => {
    input.value = "";
    clearTranscriptDraft();
    setRecordStatus("録音待機中");
    updatePracticeControls();
  });
  rerecordTranscript.addEventListener("click", () => {
    input.value = "";
    clearTranscriptDraft();
    void startRecording();
  });
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
    clearTranscriptDraft();
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
  loadTranslationPreference();
  void loadLessons();
  void checkHealth();
})();
