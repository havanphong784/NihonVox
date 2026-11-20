# Direct Voice Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use test-driven development; do not commit (the project is not a Git repository).

**Goal:** Let a Japanese learner speak into the website and receive a transcribed, contextual Japanese assistant reply with optional local VOICEVOX audio.

**Architecture:** Keep FastAPI as the local API and the existing plain-JavaScript chat. Add an injectable, lazy-failing local `faster-whisper` transcription service and a bounded multipart `/voice-chat` endpoint that reuses one shared session turn pipeline. Add a push-to-toggle `MediaRecorder` UI which posts audio, renders the transcript and reply, and keeps typing usable when microphone/STT is unavailable.

**Tech Stack:** Python 3.12, FastAPI, httpx, faster-whisper, multipart/form-data, vanilla JavaScript MediaRecorder, pytest, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-11-20-direct-voice-conversation-design.md`

## Global Constraints

- Only Japanese transcription in v1: `language="ja"`.
- Default Whisper model/device/compute type: `small` / `cpu` / `int8`.
- Maximum upload: 10 MiB; maximum transcription time: 120 seconds.
- Never persist uploaded audio; delete any decoder-required temporary file in `finally`.
- Never log audio contents or transcribed user text.
- A Whisper model load failure must not prevent typed `/chat` from working.
- Preserve existing `/chat`, session history, rules, first-Japanese-sentence selection, Ollama `think: false`, VOICEVOX, security headers, and loopback-only defaults.
- Keep recording permission user initiated; no recording on page load; release every microphone stream track after recording.
- Keep vanilla HTML/CSS/JS; no cloud STT, framework, bundler, microphone streaming, pronunciation scoring, or raw recording persistence.
- Default model download/cache remains local; startup loads the model once on a worker thread and health reports readiness.
- Model acquisition may require a one-time network download on first start; transcription thereafter runs locally. Do not claim offline first-run installation.

## Review Focus

1. Missing multipart dependency, malformed content type, dishonest MIME, empty body, or oversized body must fail before inference. Reject an advertised oversized Content-Length and cap the streamed multipart body (audio max 10 MiB plus at most 64 KiB envelope) before calling multipart parsing, so a chunked or dishonest request cannot spool an unbounded upload.
2. Whisper generator iteration itself performs work; segment iteration and transcription must run off the event loop, with serialization preventing unsafe concurrent inference on a single model.
3. Permission denial, missing secure context/device, unsupported MediaRecorder MIME, recorder errors, and stop with zero chunks must reset UI and release every acquired audio track.
4. A transcription timeout must not leave the microphone active or leak/retain a temporary recording file. Since cancelling `asyncio.to_thread` cannot stop native inference, shield the worker and keep its model lock and temp-file cleanup alive until the worker finishes even when the HTTP request has returned 504.
5. Clear-session during queued/in-flight voice turns must preserve the existing per-session ordering/reset semantics; a speech-stage failure must not pollute history or call Ollama/VOICEVOX.

---

## File Structure

- `server.py`: settings, model lifecycle/readiness, common chat-turn service, bounded API route, health response.
- `speech.py` (new): Whisper configuration adapter, injectable transcription interface, bounded temp-file lifecycle, Japanese segment joining.
- `static/index.html`: microphone controls, elapsed timer, accessible status/transcript region.
- `static/app.js`: MediaRecorder lifecycle, microphone cleanup, upload, UI states, shared successful-turn rendering.
- `static/style.css`: responsive recording/status states and disabled/error/focus styles.
- `requirements.txt`: faster-whisper and multipart parser dependency.
- `scripts/run.sh`: dependency presence and first-run/model configuration guidance without auto-downloading during every run.
- `tests/test_speech.py` (new): speech input and transcription unit tests.
- `tests/test_api.py`: health and `/voice-chat` contract/integration tests.
- `tests/test_frontend.js`: fake MediaRecorder/getUserMedia behavior tests.
- `README.md`: local model installation, cache, microphone permissions, accepted formats, privacy, and troubleshooting.
- `TEST_RESULTS.md`: final voice integration/test outcome, including hardware/service limitations.

## Task 1: Refactor shared text turns without changing chat behavior

**Files:** `server.py`; test `tests/test_api.py`.

**Interfaces:**
- Consumes existing `Session`, `ChatInput`, `ChatOutput`, `ollama_reply`, `synthesize`, and tests.
- Produces `async def process_text_turn(session_id: str, text: str) -> ChatOutput`, used by both JSON and voice routes.

- [x] **Step 1: Write regression tests** `test_chat_uses_shared_turn_pipeline`, `test_failed_turn_does_not_pollute_history`, `test_clear_waits_for_inflight_turn` and `test_rule_and_ollama_chat_contract_remains_unchanged`. Assert text response fields, history order, errors, and reset synchronization.
- [x] **Step 2: Verify red** Run `.venv/bin/pytest -q tests/test_api.py -k 'shared_turn_pipeline or failed_turn or clear_waits or chat_contract'`; expected missing helper/contract failure.
- [x] **Step 3: Extract `process_text_turn(session_id, text)`** from the existing `/chat` route; keep validation in `ChatInput`, and preserve the existing session reservation/locking/finally logic and audio fallback exactly.
- [x] **Step 4: Make `POST /chat` delegate to `process_text_turn`** and verify its response schema remains unchanged.
- [x] **Step 5: Run `.venv/bin/pytest -q tests/test_api.py tests/test_rules.py`**; expected all existing and new API/rule tests pass.

## Task 2: Local Whisper adapter, lifecycle, and bounded voice endpoint

**Files:** Create `speech.py`, `tests/test_speech.py`; modify `server.py`, `requirements.txt`, `tests/test_api.py`.

**Interfaces:**
- Consumes `process_text_turn(session_id, text) -> ChatOutput` from Task 1.
- `speech.py` exports `class SpeechTranscriber`, `def load_transcriber(model_name: str, device: str, compute_type: str, download_root: Path) -> SpeechTranscriber`, and `def transcribe_japanese(transcriber, audio: BinaryIO, suffix: str) -> str`.
- `Settings` adds `whisper_model="small"`, `whisper_device="cpu"`, `whisper_compute_type="int8"`, `whisper_download_root=BASE_DIR / "runtime" / "whisper"`, `max_recording_bytes=10 * 1024 * 1024`, and `transcription_timeout=120.0`; `from_env()` reads `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_DOWNLOAD_ROOT`, `MAX_RECORDING_BYTES`, and `TRANSCRIPTION_TIMEOUT`.
- `POST /voice-chat` accepts FastAPI `UploadFile = File(...)` and `session_id: SessionId = Form("default")`; success extends `ChatOutput` with `transcript` and returns exactly the existing reply/source/session/audio fields plus transcript.
- The app factory accepts an optional injected transcriber for tests; model load exceptions populate `app.state.speech_error`, not a startup crash.

- [x] **Step 1: Write failing `tests/test_speech.py`**: `test_joins_nonempty_segments_in_order`, `test_rejects_empty_audio`, `test_unsupported_suffix_is_rejected`, `test_temp_recording_is_removed_after_success_and_failure`, and `test_transcribe_forces_japanese_vad_and_beam_size_five`. Assert literal Japanese transcripts, exact kwargs, and no surviving temp files.
- [x] **Step 2: Verify red** Run `.venv/bin/pytest -q tests/test_speech.py -v`; expected `ModuleNotFoundError: speech`.
- [x] **Step 3: Implement `speech.py`** with an injectable model interface; invoke `transcribe(..., language="ja", task="transcribe", vad_filter=True, beam_size=5)`, then eagerly consume the segment generator within the worker call; accept only server-selected `.webm`, `.ogg`, `.wav`, or `.mp4` temp suffixes, and always unlink the unique temp file.
- [x] **Step 4: Verify green** Run `.venv/bin/pytest -q tests/test_speech.py -v`; expected all speech unit tests pass without downloading Whisper (inject fake model).
- [x] **Step 5: Write failing `/voice-chat` tests**: `test_voice_chat_returns_transcript_and_reuses_session`, `test_voice_chat_forces_japanese_and_existing_ollama_payload`, `test_voice_health_reports_model_readiness`, `test_unavailable_whisper_preserves_typed_chat`, `test_empty_audio_does_not_invoke_transcriber`, `test_oversized_audio_is_rejected_before_full_read`, `test_unsupported_mime_is_rejected`, `test_empty_transcription_does_not_call_ollama`, `test_transcription_failure_does_not_call_ollama_or_voicevox`, `test_transcription_timeout_is_504`, and `test_uploaded_recording_is_not_retained`.
- [x] **Step 6: Verify red** Run `.venv/bin/pytest -q tests/test_api.py -k 'voice_chat or voice_health or unavailable_whisper or empty_audio or oversized_audio or unsupported_mime or empty_transcription or transcription_failure or transcription_timeout or recording_is_not_retained' -v`; expected missing endpoint/readiness behavior.
- [x] **Step 7: Add a request-body size guard before multipart parsing**: reject `Content-Length > max_recording_bytes + 64 KiB`; count streamed ASGI request-body bytes and abort before multipart parsing above that same request envelope bound; then read audio at most `max_recording_bytes + 1`, rejecting `>10 MiB`, unsupported MIME/extension, and empty bytes. Close `UploadFile` in all paths and ignore the client filename.
- [x] **Step 8: Load Whisper once in lifespan** by `await asyncio.to_thread(load_transcriber, ...)`; catch model/download errors, set readiness/error state, and keep the server alive. Serialize transcription per model with an `asyncio.Lock` and run the complete transcription (including generator consumption) in a worker thread with a 120-second timeout. Shield the worker from request cancellation; on timeout return 504 while a cleanup coroutine holds the model lock until inference exits, and let the speech adapter delete its temporary input in `finally` after native inference actually finishes.
- [x] **Step 9: Add `speech_model` to `/health`**, including every existing health assertion: true only after successful load; `status` is `degraded` unless Ollama, model, VOICEVOX, and speech model are all healthy.
- [x] **Step 10: Implement `POST /voice-chat`**: validate/request bound, transcribe, reject blank transcript, and call `process_text_turn(session_id, transcript)`; add transcript to successful JSON response. Missing speech model returns 503; timeout returns 504; no-speech/invalid upload returns 422.
- [x] **Step 11: Add compatible runtime dependencies**: `faster-whisper>=1.1,<2` and `python-multipart>=0.0.20,<1` to `requirements.txt`.
- [x] **Step 12: Verify backend integration** Run `.venv/bin/pytest -q tests/test_speech.py tests/test_api.py tests/test_rules.py`; expected all tests pass, including no downstream calls on speech failure and typed-chat fallback with unavailable model.

## Task 3: Voice recording UI and browser behavior

**Files:** Modify `static/index.html`, `static/app.js`, `static/style.css`, `tests/test_frontend.js`.

**Interfaces:**
- Consumes `POST /voice-chat` multipart contract from Task 2 and the existing safe `appendMessage`, `attachAudio`, `request`, `setBusy`, session ID, and replay behavior.
- New controls: `#record-button`, `#record-status`, `#record-timer`; new JS voice functions `startRecording()`, `stopRecording()`, `releaseMicrophone()`, and `submitRecording(blob, mimeType)`.
- MIME preference: `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, `audio/mp4`; map to `.webm`, `.ogg`, `.mp4` upload filename respectively.

- [x] **Step 1: Extend fake DOM tests** to expose `navigator.mediaDevices.getUserMedia`, stream tracks, `MediaRecorder.isTypeSupported`, `MediaRecorder.start/stop/dataavailable/error`, FormData, and timers.
- [x] **Step 2: Write failing UI tests** `test_record_button_requests_microphone_only_on_click`, `test_recording_toggles_to_stop_and_shows_elapsed_time`, `test_stop_uploads_audio_with_saved_session`, `test_voice_success_renders_transcript_then_reply_and_source`, `test_permission_denied_keeps_text_composer_enabled`, `test_unsupported_recorder_shows_clear_message`, `test_zero_recording_chunks_do_not_submit`, `test_recorder_error_releases_tracks_and_preserves_chat`, `test_duplicate_record_click_does_not_open_second_stream`, and `test_clear_stops_active_recording_and_releases_tracks`.
- [x] **Step 3: Verify red** Run `node --test tests/test_frontend.js`; expected missing controls/functions or unmet assertions.
- [x] **Step 4: Add accessible microphone UI** to `static/index.html`: a real button, a polite `role="status"` region, elapsed-time text, and direct permission explanation; do not remove/disable the text composer when microphone is unavailable.
- [x] **Step 5: Implement a single recorder state machine** in `static/app.js`: request permission only from button click; select a supported MIME; collect `dataavailable` chunks; on stop, stop all tracks before posting; send multipart `audio` and `session_id`; suppress submit when blob is empty; post once only; reset timer and controls on success/failure.
- [x] **Step 6: Reuse safe chat presentation**: append transcript first as a user message labelled `giọng nói`, append assistant reply with `rule`/`ollama`, use existing audio attachment/autoplay/replay, and preserve last replay on failed voice requests. Never insert transcript HTML.
- [x] **Step 7: Implement recovery paths** for insecure context or missing `getUserMedia`, `NotAllowedError`, `NotFoundError`, `NotReadableError`, unsupported MIME, recorder error, fetch error, backend no-speech/422, and clear while recording; keep the textarea usable in all non-processing states.
- [x] **Step 8: Style desktop/mobile recording states** in `static/style.css`; ensure 390px width has no horizontal overflow, visible focus/disabled/error states, and reduced-motion support.
- [x] **Step 9: Verify frontend tests** Run `node --test tests/test_frontend.js && node --check static/app.js`; expected all frontend behavior tests pass.

## Task 4: Install/run guidance and end-to-end verification

**Files:** Modify `README.md`, `scripts/run.sh`, `TEST_RESULTS.md`; use `tests/stub_services.py` only if useful for downstream audio.

**Interfaces:**
- Consumes final `/voice-chat` contract, config variables, health fields, and UI copy.
- No new persistent audio upload or transcript database.

- [x] **Step 1: Document setup**: pip installation of `faster-whisper` plus `python-multipart`; first launch downloads `small` into the configured local cache; hardware/model size options; microphone permission is only requested on click; localhost is a secure context; unsupported browsers/permission failure keep text chat usable; raw recordings are not retained.
- [x] **Step 2: Document API** with a curl multipart example (`curl -F audio=@sample.wav -F session_id=default http://127.0.0.1:8000/voice-chat`), response fields, validation/errors and health `speech_model` status.
- [x] **Step 3: Run full automation**: `.venv/bin/pip install -r requirements.txt`, `.venv/bin/pytest -q`, `node --test tests/test_frontend.js`, `uv pip check --python .venv/bin/python`, `node --check static/app.js`, `bash -n scripts/run.sh`.
- [x] **Step 4: Run the app** with `./scripts/run.sh`; verify `curl http://127.0.0.1:8000/` and `/health`, then post a valid small WAV to `/voice-chat` and verify transcript, Ollama source, session ID and audio fallback.
- [x] **Step 5: Exercise browser with a generated local Japanese test recording**: grant microphone when prompted, click `Nói`, speak one Japanese sentence, click `Dừng`, check transcript and reply appear in order, audio playback/replay if available, and clear-session behavior.
- [x] **Step 6: Verify denial/offline cases**: deny permission, test empty/silent audio, set Ollama/VOICEVOX offline via isolated app configurations, and verify short localized errors/text fallback while no existing local services are stopped.
- [x] **Step 7: Verify mobile viewport** at 390×844; capture screenshot and check no horizontal page overflow and reachable recording controls.
- [x] **Step 8: Update `TEST_RESULTS.md`** with exact command outputs and candidly state whether real Whisper model download/inference and real VOICEVOX playback were verified or tested with injected/model/audio fixtures.


## Execution outcome

- 91 targeted backend/rule/speech tests pass; full pytest (including the Node wrapper) and 25 direct Node frontend tests are recorded in `TEST_RESULTS.md`.
- Real local `faster-whisper small` decoded Japanese speech synthesized by local VOICEVOX; `/voice-chat` used real Ollama and VOICEVOX and returned HTTP 200.
- A fresh whole-project reviewer found an Important asynchronous recorder-error race. Added RED→GREEN tests for partial uploads and stale `stop` events, isolated state per recorder, and verified all frontend tests again.
- Ruling: the requested project directory is not a Git repository, so implementation and ledger are kept in place without worktree, commit, or Git review package; no Git history was changed.
- Ruling: PyAV 19 in the resolved environment removed the keyword expected by `faster-whisper` 1.x; pin `av>=12,<19`, verify real decoder behavior, and retain that compatibility bound.
- Remaining physical-device limitation: no user speech was captured during browser testing. Browser permission/device discovery succeeded, UI was checked at desktop/mobile sizes, and real Japanese audio was exercised through the actual backend instead.
