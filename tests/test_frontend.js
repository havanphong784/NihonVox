"use strict";
// Dependency-free behavioral tests: execute the real app.js against a tiny DOM adapter.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../static/app.js"), "utf8");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.attributes = {};
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.scrollHeight = 500;
  }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  async fire(name, properties = {}) {
    if (name === "click" && this.disabled) return;
    const event = { preventDefault() {}, ...properties };
    for (const listener of this.listeners[name] || []) await listener(event);
  }
  querySelectorAll(selector) { return this.children.filter(e => selector === ".message" && e.className?.split(" ").includes("message")); }
  remove() { this.parent.children = this.parent.children.filter(e => e !== this); }
  focus() {}
  requestSubmit() { return this.fire("submit"); }
}

function setup(options = {}) {
  const elements = new Map();
  for (const id of ["chat-form", "message-input", "send-button", "clear-button", "replay-button", "health-button", "record-button", "record-status", "record-timer", "messages", "empty-state", "processing", "latency", "error-message", "audio-message", "health-message", "ollama-status", "voicevox-status", "speech-status", "model-status"]) elements.set(id, new Element());
  const get = id => elements.get(id);
  get("replay-button").disabled = true;
  const calls = [];
  const timeouts = [];
  const audios = [];
  const tracks = [];
  const recorders = [];
  function createStream() {
    const track = { stopped: false, stop() { this.stopped = true; } };
    tracks.push(track);
    return { getTracks: () => [track] };
  }
  let getUserMediaCalls = 0;
  let getUserMediaError = null;
  let resolvePermission = null;
  let activeRecorder = null;
  let respond = () => ({ reply: "こんにちは。", source: "rule", audio_url: "/audio/" + "a".repeat(32) + ".wav" });
  const storage = new Map();
  class Audio extends Element {
    constructor(url) { super("audio"); this.src = url; this.plays = 0; this.currentTime = 0; audios.push(this); }
    pause() {}
    async play() { this.plays++; if (options.blockAutoplay) throw new DOMException("blocked", "NotAllowedError"); await this.fire("play"); }
  }
  class FakeBlob {
    constructor(parts, opts = {}) { this.parts = parts; this.type = opts.type || ""; this.size = parts.reduce((n, part) => n + (part.size || String(part).length), 0); }
  }
  class FakeFormData {
    constructor() { this.fields = []; }
    append(name, value, filename) { this.fields.push({ name, value, filename }); }
  }
  class FakeMediaRecorder extends Element {
    static isTypeSupported(type) { return options.unsupportedMime ? false : ["audio/webm;codecs=opus", "audio/webm"].includes(type); }
    constructor(stream, opts = {}) { super("recorder"); this.stream = stream; this.mimeType = opts.mimeType || "audio/webm"; this.state = "inactive"; activeRecorder = this; recorders.push(this); }
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; if (!options.emptyRecording) void this.fire("dataavailable", { data: new FakeBlob(["audio"], { type: this.mimeType }) }); void this.fire("stop"); }
  }
  const context = {
    document: { getElementById: get, createElement: tag => new Element(tag) },
    localStorage: {
      getItem(key) { if (options.blockStorage) throw new Error("denied"); return storage.get(key) || null; },
      setItem(key, value) { if (options.blockStorage) throw new Error("denied"); storage.set(key, value); },
    },
    fetch: async (url, opts = {}) => {
      calls.push({ url, ...opts });
      if (url === "/health") return { ok: true, json: async () => ({ ollama: true, model: true, voicevox: true, speech_model: true }) };
      if (opts.method === "DELETE") return { ok: true, json: async () => ({ status: "cleared" }) };
      const data = await respond();
      return { ok: !data.detail, json: async () => data };
    },
    navigator: { mediaDevices: { getUserMedia: async () => {
      getUserMediaCalls++;
      if (getUserMediaError) throw getUserMediaError;
      if (options.permissionPending) return new Promise(resolve => { resolvePermission = resolve; });
      return createStream();
    } } },
    MediaRecorder: FakeMediaRecorder, Blob: FakeBlob, FormData: FakeFormData,
    Audio, AbortController, TypeError, performance, Date,
    setTimeout: (fn, ms) => { timeouts.push(ms); return setTimeout(fn, ms); },
    clearTimeout, setInterval, clearInterval,
  };
  vm.runInNewContext(source, context, { filename: "app.js" });
  return { get, calls, audios, storage, tracks, recorders, timeouts, Blob: FakeBlob, respond: fn => { respond = fn; },
    getUserMediaCalls: () => getUserMediaCalls,
    grantPermission: () => resolvePermission?.(createStream()),
    setGetUserMediaError: error => { getUserMediaError = error; },
    activeRecorder: () => activeRecorder,
    async submit(text) { get("message-input").value = text; await get("chat-form").fire("submit"); },
    chats() { return calls.filter(c => c.url === "/chat"); },
    voiceChats() { return calls.filter(c => c.url === "/voice-chat"); },
  };
}

test("rule response renders as text and local audio can replay", async () => {
  const app = setup();
  await app.submit("お茶");
  assert.equal(app.chats().length, 1);
  assert.deepEqual(JSON.parse(app.chats()[0].body), { text: "お茶", session_id: "default" });
  const articles = app.get("messages").querySelectorAll(".message");
  assert.equal(articles[1].children[1].textContent, "こんにちは。");
  assert.equal(app.audios.length, 1);
  await app.get("replay-button").fire("click");
  assert.equal(app.audios[0].plays, 2);
});

test("empty input does not send a request", async () => {
  const app = setup();
  await app.submit("  \n ");
  assert.equal(app.chats().length, 0);
  assert.match(app.get("error-message").textContent, /Vui lòng nhập/);
});

test("composition and Shift Enter do not send, ordinary Enter does", async () => {
  const app = setup();
  const input = app.get("message-input");
  input.value = "お茶";
  await input.fire("compositionstart");
  await input.fire("keydown", { key: "Enter" });
  await input.fire("compositionend");
  await input.fire("keydown", { key: "Enter", shiftKey: true });
  assert.equal(app.chats().length, 0);
  await input.fire("keydown", { key: "Enter", isComposing: true });
  assert.equal(app.chats().length, 0);
  await input.fire("keydown", { key: "Enter", shiftKey: false });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.chats().length, 1);
});

test("send is disabled while waiting and duplicate submissions are ignored", async () => {
  const app = setup();
  let finish;
  app.respond(() => new Promise(resolve => { finish = resolve; }));
  const pending = app.submit("お茶");
  assert.equal(app.get("send-button").disabled, true);
  assert.equal(app.get("processing").hidden, false);
  await app.submit("アイス");
  assert.equal(app.chats().length, 1);
  finish({ reply: "こんにちは。", source: "rule", audio_url: null });
  await pending;
  assert.equal(app.get("send-button").disabled, false);
});

test("blocked storage and autoplay do not break conversation", async () => {
  const app = setup({ blockStorage: true, blockAutoplay: true });
  await app.submit("お茶");
  assert.equal(app.get("send-button").disabled, false);
  assert.equal(app.get("replay-button").disabled, false);
  assert.match(app.get("audio-message").textContent, /Bấm “Phát”/);
});

test("text is rendered without interpreting malicious HTML", async () => {
  const app = setup();
  const hostile = '<img src=x onerror="alert(1)">こんにちは。';
  app.respond(() => ({ reply: hostile, source: "ollama", audio_url: null }));
  await app.submit(hostile);
  const articles = app.get("messages").querySelectorAll(".message");
  assert.equal(articles[0].children[1].textContent, hostile);
  assert.equal(articles[1].children[1].textContent, hostile);
  assert.equal(articles[1].children[1].children.length, 0);
});

test("reset sends DELETE to saved default session and clears messages", async () => {
  const app = setup();
  await app.submit("お茶");
  await app.get("clear-button").fire("click");
  assert.ok(app.calls.some(c => c.url === "/sessions/default" && c.method === "DELETE"));
  assert.equal(app.get("messages").querySelectorAll(".message").length, 0);
  assert.equal(app.get("replay-button").disabled, true);
  assert.equal(app.get("empty-state").hidden, false);
});

test("backend errors display Vietnamese text and preserve input for retry", async () => {
  const app = setup();
  app.respond(() => ({ detail: "Ollama đang offline." }));
  await app.submit("こんにちは");
  assert.match(app.get("error-message").textContent, /Ollama đang offline/);
  assert.equal(app.get("message-input").value, "こんにちは");
  assert.equal(app.get("send-button").disabled, false);
});

test("failed new turn preserves replay of the latest successful reply", async () => {
  const app = setup();
  await app.submit("お茶");
  app.respond(() => ({ detail: "Ollama đang offline." }));
  await app.submit("こんにちは");
  assert.equal(app.get("replay-button").disabled, false);
  await app.get("replay-button").fire("click");
  assert.equal(app.audios[0].plays, 2);
});

test("a new text-only reply disables replay rather than replaying an older reply", async () => {
  const app = setup();
  await app.submit("お茶");
  app.respond(() => ({ reply: "そうですね。", source: "ollama", audio_url: null, error_audio: "VOICEVOX đang offline." }));
  await app.submit("こんにちは");
  assert.equal(app.get("replay-button").disabled, true);
  const articles = app.get("messages").querySelectorAll(".message");
  assert.equal(articles.at(-1).children.at(-1).textContent, "VOICEVOX đang offline.");
});

test("network failure has a readable Vietnamese error", async () => {
  const app = setup();
  app.respond(() => { throw new TypeError("Failed to fetch"); });
  await app.submit("こんにちは");
  assert.match(app.get("error-message").textContent, /Không kết nối được server/);
});

test("timeout has a readable Vietnamese error", async () => {
  const app = setup();
  app.respond(() => { throw new DOMException("aborted", "AbortError"); });
  await app.submit("こんにちは");
  assert.match(app.get("error-message").textContent, /Hết thời gian chờ/);
});

test("an external audio URL is rejected without making an audio request", async () => {
  const app = setup();
  app.respond(() => ({ reply: "こんにちは。", source: "ollama", audio_url: "https://evil.example/file.wav" }));
  await app.submit("こんにちは");
  assert.equal(app.audios.length, 0);
  assert.match(app.get("audio-message").textContent, /không hợp lệ/);
});

test("record button requests microphone only on click", async () => {
  const app = setup();
  assert.equal(app.getUserMediaCalls(), 0);
  await app.get("record-button").fire("click");
  assert.equal(app.getUserMediaCalls(), 1);
  assert.equal(app.get("record-button").textContent, "Dừng");
  assert.equal(app.get("record-status").textContent, "Đang ghi âm...");
  await app.get("record-button").fire("click");
});

test("recording toggles to stop, uploads audio with saved session, and renders transcript then reply", async () => {
  const app = setup();
  app.respond(() => ({ transcript: "昨日、映画を見ました。", reply: "何の映画を見ましたか？", source: "ollama", audio_url: null }));
  await app.get("record-button").fire("click");
  await app.get("record-button").fire("click");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.voiceChats().length, 1);
  assert.ok(app.timeouts.includes(300000));
  assert.match(app.voiceChats()[0].body.fields.find(field => field.name === "session_id").value, /^default$/);
  const articles = app.get("messages").querySelectorAll(".message");
  assert.equal(articles[0].children[1].textContent, "昨日、映画を見ました。");
  assert.equal(articles[1].children[1].textContent, "何の映画を見ましたか？");
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.get("record-status").textContent, "録音待機中");
});

test("permission denial keeps text composer enabled and shows recovery text", async () => {
  const app = setup();
  app.setGetUserMediaError(new DOMException("permission denied", "NotAllowedError"));
  await app.get("record-button").fire("click");
  assert.match(app.get("record-status").textContent, /microphone|quyền/i);
  assert.equal(app.get("send-button").disabled, false);
  assert.equal(app.get("message-input").disabled, false);
});

test("unsupported recorder shows a clear message without requesting microphone", async () => {
  const app = setup({ unsupportedMime: true });
  await app.get("record-button").fire("click");
  assert.equal(app.getUserMediaCalls(), 0);
  assert.match(app.get("record-status").textContent, /trình duyệt|MediaRecorder/i);
});

test("zero recording chunks do not submit", async () => {
  const app = setup({ emptyRecording: true });
  await app.get("record-button").fire("click");
  await app.get("record-button").fire("click");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.voiceChats().length, 0);
  assert.match(app.get("record-status").textContent, /Không nhận được âm thanh|rỗng/i);
  assert.equal(app.tracks[0].stopped, true);
});

test("clear stops active recording and releases tracks", async () => {
  const app = setup();
  await app.get("record-button").fire("click");
  await app.get("clear-button").fire("click");
  assert.equal(app.activeRecorder().state, "inactive");
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.get("record-status").textContent, "録音待機中");
});


test("system check reports local Whisper readiness", async () => {
  const app = setup();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.get("speech-status").textContent, "Whisper local: Online");
  app.respond(() => ({ detail: "unused" }));
});


test("pending microphone permission is announced and duplicate requests are prevented", async () => {
  const app = setup({ permissionPending: true });
  const pending = app.get("record-button").fire("click");
  await new Promise(resolve => setImmediate(resolve));
  assert.match(app.get("record-status").textContent, /xin quyền microphone/i);
  assert.equal(app.get("record-button").disabled, true);
  await app.get("record-button").fire("click");
  assert.equal(app.getUserMediaCalls(), 1);
  app.grantPermission();
  await pending;
  assert.equal(app.get("record-button").textContent, "Dừng");
  await app.get("record-button").fire("click");
});


test("clear cancels a pending microphone permission and stops any late stream", async () => {
  const app = setup({ permissionPending: true });
  const pending = app.get("record-button").fire("click");
  await new Promise(resolve => setImmediate(resolve));
  await app.get("clear-button").fire("click");
  app.grantPermission();
  await pending;
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.voiceChats().length, 0);
  assert.equal(app.activeRecorder(), null);
  assert.equal(app.get("record-button").textContent, "Nói");
});

test("recorder error releases microphone tracks and leaves text chat usable", async () => {
  const app = setup();
  await app.get("record-button").fire("click");
  await app.activeRecorder().fire("error");
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.get("record-button").disabled, false);
  assert.equal(app.get("message-input").disabled, false);
  assert.match(app.get("record-status").textContent, /Microphone gặp lỗi/);
});


test("recorder error discards its partial recording when a late stop event arrives", async () => {
  const app = setup();
  await app.get("record-button").fire("click");
  const failedRecorder = app.recorders[0];
  await failedRecorder.fire("dataavailable", { data: new app.Blob(["partial"], { type: "audio/webm" }) });
  await failedRecorder.fire("error");
  await failedRecorder.fire("stop");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.voiceChats().length, 0);
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.get("record-status").textContent, "Microphone gặp lỗi; hãy thử lại hoặc nhập bằng bàn phím");
});

test("late stop from a failed recorder cannot interrupt a newer recording", async () => {
  const app = setup();
  await app.get("record-button").fire("click");
  const failedRecorder = app.recorders[0];
  await failedRecorder.fire("error");
  await app.get("record-button").fire("click");
  const activeRecorder = app.recorders[1];
  await failedRecorder.fire("stop");
  assert.equal(app.get("record-button").textContent, "Dừng");
  assert.equal(app.get("record-status").textContent, "Đang ghi âm...");
  assert.equal(app.tracks[1].stopped, false);
  await app.get("record-button").fire("click");
  await activeRecorder.fire("stop");
});
