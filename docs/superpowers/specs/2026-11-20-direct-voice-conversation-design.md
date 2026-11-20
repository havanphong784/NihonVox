# Direct Voice Conversation Design

**Date:** 2026-11-20

## Intent

Turn the existing local Japanese practice chat into a voice-first AI conversation assistant. A learner speaks Japanese into the browser, sees the local transcription, receives a contextual Japanese reply from Ollama, and hears the reply from VOICEVOX. Typing remains available as a fallback.

```text
Bấm “Nói” → nói tiếng Nhật → bấm “Dừng” → transcript
→ Ollama/luật hội thoại → câu trả lời tiếng Nhật → VOICEVOX → phát audio
```

## Goals

- Record microphone audio directly in the browser with an explicit permission prompt.
- Use local speech-to-text with `faster-whisper`, Japanese language forced to `ja`.
- Preserve the existing Ollama conversation history and rule fast paths.
- Show the learner's transcript and assistant's reply as separate messages.
- Auto-submit a non-empty transcript after recording stops.
- Keep keyboard text chat working.
- Explain microphone, speech model, Ollama, and VOICEVOX failures without breaking text fallback.
- Never persist raw microphone recordings.

## Non-goals

- Streaming audio, browser voice-activity detection, pronunciation scoring, phoneme alignment, grammar correction, multi-speaker sessions, cloud speech recognition, or removing `/chat`.

## Anti-goals

- Do not request microphone permission on page load.
- Do not send audio to Ollama or use a remote STT fallback.
- Do not claim transcript accuracy.
- Do not add a frontend framework or bundler.

## Chosen approach

### Browser Web Speech API

Rejected: browser support and recognition backends vary, and local-only behavior is unclear.

### Browser `MediaRecorder` plus local `faster-whisper` — chosen

The browser records a bounded WebM/Opus, Ogg/Opus, WAV, or MP4 clip. FastAPI receives it as multipart data, passes it to a singleton `WhisperModel`, and reuses the existing text conversation and VOICEVOX pipeline. This keeps audio local and consistent across browsers with `MediaRecorder`, at the cost of an initial model download and CPU inference latency.

### Voxtype-only integration

Rejected as the primary path: it supplies text to the existing form but is not direct website microphone conversation.

## Backend design

Extend `Settings` with `WHISPER_MODEL=small`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`, `MAX_RECORDING_BYTES=10 MiB`, `TRANSCRIPTION_TIMEOUT=120`, and an optional local model cache path. Load the Whisper model once during lifespan startup. A load failure must not stop typed `/chat`; `/health` adds `speech_model` and reports `degraded`.

Add `POST /voice-chat` as multipart form data:

- `audio`: required bounded WebM/Ogg/WAV/MP4 upload;
- `session_id`: same validation as `/chat`.

Return:

```json
{
  "transcript": "昨日、友達と映画を見ました。",
  "reply": "いいですね。何の映画を見ましたか？",
  "audio_url": "/audio/<uuid>.wav",
  "source": "ollama",
  "session_id": "default",
  "error_audio": null
}
```

Reject missing/oversized/unsupported/empty audio before inference. Run `transcribe(..., language="ja", vad_filter=True, beam_size=5)` in a worker thread. Join non-empty segments, reject empty transcription, then process the text through one shared helper used by `/chat` and `/voice-chat`. The raw recording is discarded after transcription; if a decoder requires a path, use a temporary file and delete it in `finally`.

Use 422 for invalid uploads/no speech, 503 for missing model, 504 for transcription timeout, existing Ollama errors, and existing text-success/audio-fallback behavior for VOICEVOX errors. Do not log audio or user text.

## Frontend design

Add a voice panel:

```text
[🎙 Nói]
Trạng thái: Sẵn sàng
Bản chép lời sẽ xuất hiện sau khi bạn dừng ghi âm.
```

States: idle, permission request, recording with elapsed time and `Dừng`, transcribing, sending, permission denied, no speech, and backend error. Use `navigator.mediaDevices.getUserMedia({audio: true})` and `MediaRecorder`; choose the first supported MIME from `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, and `audio/mp4`. Stop all tracks after recording. If unsupported, keep typing available.

After success, render the transcript as a learner message labeled `giọng nói`, render the assistant response with `rule`/`ollama`, use `textContent`, autoplay/playback behavior, replay state, and latest-message scrolling. Auto-submit non-empty transcripts after stop. The first version uses toggle recording (`Nói` then `Dừng`), forces Whisper language to Japanese, and keeps the textarea as fallback without an extra confirmation step.

## Tests and success criteria

Add tests first for bounded upload reads, MIME validation, empty/no-speech/model-unavailable paths, injected transcription plus session history/Ollama payload, no raw audio retention, transcription failures not calling downstream services, MediaRecorder states, permission denial, empty transcript, duplicate controls, safe rendering, browser smoke, and mobile layout.

Success means a learner can open `http://127.0.0.1:8000`, grant permission, press `Nói`, speak Japanese, press `Dừng`, see the transcript and Japanese response in the same conversation, and hear the response when VOICEVOX is available. Dependency failures must identify the failing stage and leave text chat usable.
