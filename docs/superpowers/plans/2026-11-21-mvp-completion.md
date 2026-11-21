# NihonVox MVP Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NihonVox a reliable five-turn Japanese speaking practice MVP with three quick lessons, transcript approval before sending, explicit translation control, and evidence-backed acceptance tests.

**Architecture:** Keep the current FastAPI + vanilla HTML/CSS/JS architecture. Extract transcription into a session-free `/transcribe` endpoint while preserving `/voice-chat` for API compatibility; add lesson presets and bounded progress to the existing in-memory session model. The browser will use `/transcribe` → editable draft → `/chat`, while typed chat and the legacy voice endpoint continue to work.

**Tech Stack:** Python 3.10+, FastAPI/Pydantic/httpx, faster-whisper, Ollama, VOICEVOX, Google translation adapter, vanilla JavaScript/CSS, pytest, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-11-20-mvp-completion-design.md`

## Global Constraints

- Keep FastAPI, HTML/CSS/JS, Whisper, Ollama, VOICEVOX and the existing translation adapter; add no framework, database, account system, or new dependency.
- Keep `/voice-chat` backward compatible; the new UI uses `/transcribe` then `/chat`.
- Three quick lessons are `order-food`, `introduce-yourself`, and `ask-directions`; each has exactly 5 counted learner turns and a fixed Japanese/Vietnamese practice sentence.
- Every non-empty submitted learner input that receives a valid Japanese reply counts; no Japanese-character or grammar gate is added.
- Invalid transcription, failed send, or invalid model reply does not count and does not enter session history; a valid reply still counts when TTS or translation fails.
- Preserve local-only privacy: no transcript/content telemetry, no persistent audio, no server-side persistence beyond current in-memory sessions.
- Translation is browser-opt-in and defaults off for a browser without a saved preference; `TRANSLATION_ENABLED=0` overrides the UI.
- Do not claim the five-person learner acceptance target until real participants complete the separate test script.
- Do not commit or push unless the user explicitly requests it.

## Review Focus

- A repeated click or delayed recorder event must not create a duplicate transcript or chat turn — Task 4 adds a JS regression test for stale recorder generations and double-submit guards.
- A `/transcribe` upload must never mutate session history or call Ollama, VOICEVOX, or Google — Task 2 adds an endpoint isolation test.
- A retry after an invalid model reply must not duplicate the learner input, while a TTS/translation failure must preserve the successful turn — Task 1 adds both history assertions.
- A completed lesson must reject the sixth turn, including concurrent requests, without corrupting its `0/5…5/5` progress — Task 1 adds a locked-session concurrency test.
- Translation must remain off when either the browser toggle is off or `TRANSLATION_ENABLED=0`, and must never send learner input directly — Task 3 adds transport/request assertions.

---

### Task 1: Add lesson presets and bounded practice progress

**Files:**
- Modify: `tutor.py:10-116` — lesson metadata, request/response models, prompt context.
- Modify: `server.py:123-150, 426-506` — session state, practice-session creation, turn processing, progress response.
- Test: `tests/test_practice_api.py` — preset, progress, completion, and concurrency coverage.
- Test: `tests/test_api.py` — history behavior on failed and partial-success turns.

**Interfaces:**
- Consumes: existing `LearningPreferences`, `TutorReply`, `request_ollama_reply()`, and `Session` locking.
- Produces: `LESSON_PRESETS`/lesson lookup in `tutor.py`; `GET /lessons` returning quick-lesson IDs, labels, goals and default metadata from that single source; optional `lesson_id` on practice-session creation; a response `progress` object for quick lessons with `lesson_id`, `completed_turns`, `total_turns`, `completed`, and optional `practice_sentence`; 409 after completion.

- [ ] **Step 1: Write failing tests for the lesson contract**
  - Add tests for each lesson ID returning its exact preset metadata and rejecting an unknown ID with 422 before any Ollama call.
  - Add a `GET /lessons` test that returns the three preset IDs, labels, goals, and defaults from the backend source of truth.
  - Add a test that `POST /practice-sessions` with `lesson_id="order-food"` returns a session and `progress.completed_turns == 0`, `total_turns == 5`.
  - Add tests that successful typed turns move progress 0→1→…→5, that the opener is not counted, and that the sixth turn returns 409.
  - Add a test that a non-empty Vietnamese-only input still counts after a valid model reply.
  - Add tests that an invalid model reply/upstream failure leaves both history and progress unchanged, while an audio or translation failure retains the history/progress turn.
  - Add an async concurrent-send test at progress 4 proving exactly one request reaches 5 and the other receives 409 or a serialized valid response without progress >5.

- [ ] **Step 2: Run the focused tests and verify they fail**
  - Run `pytest -q tests/test_practice_api.py tests/test_api.py`.
  - Expected: failures for missing lesson IDs/progress/409 semantics, with all pre-existing tests still identifying the changed contract rather than import errors.

- [ ] **Step 3: Implement lesson metadata and progress**
  - In `tutor.py`, define the three preset records with the exact IDs, level/topic, learner goal, role/context instruction, and fixed Japanese/Vietnamese practice sentence from the approved spec. Add a lookup that raises a caller-handled validation error for unknown IDs.
  - Extend the practice input model with optional `lesson_id`; enforce that quick lessons use their preset metadata and existing custom preferences remain valid.
  - Add `lesson_id`, `completed_turns`, and `completed` state to `Session`; expose a compact progress model on quick-lesson responses only.
  - In the existing per-session lock, reject already-completed quick lessons with 409, call the model, validate the Japanese reply, then append user+assistant history and increment progress exactly once. Keep the increment after reply validation and before/independent of non-fatal audio/translation degradation.
  - Keep failed model requests out of history so a retained UI draft can retry without duplication. Preserve existing session expiry (410), history limits, custom lessons, and free chat behavior.

- [ ] **Step 4: Run the focused tests and verify they pass**
  - Run `pytest -q tests/test_practice_api.py tests/test_api.py`.
  - Expected: all focused tests pass, including existing custom-session and legacy-chat tests.

- [ ] **Step 5: Run the full backend suite**
  - Run `pytest -q`.
  - Expected: no regressions before frontend work begins.

### Task 2: Split browser transcription from chat submission

**Files:**
- Modify: `server.py:261-318, 507-558` — shared upload/transcription helper and new route.
- Modify: `tests/test_api.py` — `/transcribe` isolation, validation, timeout, and cleanup tests.
- Modify: `tests/test_frontend.js` — endpoint expectations used by the browser adapter, if needed.
- Modify: `README.md` — document the new endpoint and preserve legacy endpoint behavior.

**Interfaces:**
- Consumes: current `VoiceUploadLimitMiddleware`, transcription settings/lock, `transcribe_japanese()`, and existing upload validation.
- Produces: `POST /transcribe` with multipart `audio`, returning `{ "transcript": string }`; same content-type, size, timeout, decoder, and cleanup semantics as `/voice-chat`; no session or upstream side effects.

- [ ] **Step 1: Write failing endpoint tests**
  - Test a valid upload returns only the transcript and leaves the selected session history untouched.
  - Test that the transcriber is invoked once and no Ollama/VOICEVOX/translator transport request occurs.
  - Test empty/unsupported/oversized uploads, timeout, unavailable transcriber, decoder failure, and transient-file cleanup match the existing voice contract.
  - Test the old `/voice-chat` route still performs transcription plus chat exactly as before.

- [ ] **Step 2: Run the focused tests and verify the new endpoint fails**
  - Run `pytest -q tests/test_api.py -k 'transcrib or voice'`.
  - Expected: new `/transcribe` tests fail because the route/helper is absent; existing voice tests remain the baseline.

- [ ] **Step 3: Extract the shared transcription operation and add `/transcribe`**
  - Extract the read/validate/lock/timeout/to-thread/cleanup sequence into an internal async helper returning `str`, parameterized only by uploaded file and settings.
  - Route `/transcribe` through that helper and return a dedicated response model. Keep `VoiceUploadLimitMiddleware` covering both transcription endpoints, and keep `/voice-chat` calling the helper before `process_text_turn()`.
  - Do not pass `session_id` into the helper and do not call any reply/audio/translation code from `/transcribe`.

- [ ] **Step 4: Run endpoint tests and the complete backend suite**
  - Run `pytest -q tests/test_api.py -k 'transcrib or voice'`, then `pytest -q`.
  - Expected: focused and full tests pass; legacy `/voice-chat` behavior remains green.

- [ ] **Step 5: Update API documentation**
  - Add `/transcribe` curl/response/error behavior to `README.md`, explain that browser voice uses transcript approval, and retain the compatibility note for `/voice-chat` clients.

### Task 3: Make translation explicitly controllable

**Files:**
- Modify: `server.py:123-150, 456-506` — request field and per-request translation selection.
- Modify: `translation.py` only if the existing adapter needs a no-call disabled path.
- Test: `tests/test_translation.py` and `tests/test_api.py` — disabled/overridden/request-scoped translation behavior.
- Modify: `README.md` — final UI/API privacy explanation.

**Interfaces:**
- Consumes: existing `TranslationService`, `TRANSLATION_ENABLED`, cache, timeout, and `ChatOutput` fields.
- Produces: optional `translate: bool | None` on chat/practice input; effective translation is false when the server flag is false, otherwise the explicit request value or server default; no direct Google call when false.

- [ ] **Step 1: Write failing transport tests**
  - Assert `translate=false` returns null translation fields and makes no translator transport request even when the server default is enabled.
  - Assert `translate=true` uses the existing adapter when server translation is enabled and only passes the final assistant `reply`.
  - Assert `TRANSLATION_ENABLED=0` makes both explicit `true` and omitted requests return no translation and no Google request.
  - Assert translator and TTS failures still return the Japanese reply and preserve the successful lesson turn.

- [ ] **Step 2: Run focused translation tests and verify the new request behavior fails**
  - Run `pytest -q tests/test_translation.py tests/test_api.py -k 'translat or audio'`.
  - Expected: request-level toggle tests fail while existing adapter/cache tests identify the stable baseline.

- [ ] **Step 3: Implement effective translation selection**
  - Add an optional strict boolean to the relevant request models and thread it through `process_text_turn()`/`play_reply()` without changing legacy callers.
  - Compute `effective_translate = config.translation_enabled and (request value if supplied else browser/server default)`; when false, return null fields without invoking the adapter. Keep Google payload limited to the final assistant reply.
  - Ensure quick-lesson opening and turns carry the selected setting consistently, while old `/voice-chat` clients retain the server default unless they send the field.

- [ ] **Step 4: Run focused and full tests**
  - Run `pytest -q tests/test_translation.py tests/test_api.py -k 'translat or audio'`, then `pytest -q`.
  - Expected: all translation, audio fallback, and session-progress assertions pass.

### Task 4: Build the approved-transcript and quick-lesson browser flow

**Files:**
- Modify: `static/index.html:20-125` — quick lesson selector, progress display, translation toggle, transcript draft actions.
- Modify: `static/app.js:45-567` — lesson metadata/loading, transcript approval state, `/transcribe` flow, progress rendering, completion lock, translation preference, latency metrics.
- Modify: `static/style.css` — accessible draft/lesson/progress states and narrow-layout styling.
- Test: `tests/test_frontend.js` and `tests/test_frontend.py` — browser behavior and static contract.

**Interfaces:**
- Consumes: `/transcribe`, `/chat`, `/practice-sessions`, `progress`, `translation`, and existing recorder/audio/session helpers.
- Produces: a browser flow where stop → transcript draft → edit/re-record/cancel → one approved `/chat` submission; quick lessons default to `order-food`; progress and completion are visible; browser translation preference defaults off and persists locally.

- [ ] **Step 1: Write failing DOM tests for the user flow**
  - Test selecting/starting each quick lesson sends `lesson_id` and renders its goal/progress.
  - Test stop calls `/transcribe`, puts the transcript in an editable draft, and does not call `/chat` until the learner submits.
  - Test editing the draft sends the edited value once; the user message is rendered only after successful chat; a failed chat retains the draft and does not duplicate it on retry.
  - Test re-record replaces a voice draft only after successful transcription; cancel clears it; an existing unsent typed draft is not overwritten by starting recording.
  - Test stale recorder stop/results cannot affect a new recording or a newly started lesson; double click cannot send two chats.
  - Test translation toggle defaults off, persists, sends `translate`, renders returned translation, and reports server-disabled status without making client-side Google requests.
  - Test after progress 5/5 the send/record controls are disabled, replay remains available, and starting a new lesson resets the lock.
  - Test latency labels update for transcription, reply display, and `playing`/autoplay-blocked audio without treating autoplay blocking as chat failure.

- [ ] **Step 2: Run frontend tests and verify the new behavior fails**
  - Run `node --test tests/test_frontend.js`.
  - Expected: new transcript-approval, lesson, translation, and completion tests fail before implementation; existing text/IME/audio tests remain as regression coverage.

- [ ] **Step 3: Implement the browser state machine**
  - Add a distinct `transcriptDraft` state and request generation token. On stop, upload the blob to `/transcribe`; on success populate the existing composer and show explicit `Gửi transcript`/`Thu lại`/`Hủy` affordances. Do not append the learner message or call `/chat` during transcription.
  - Reuse the existing composer submission path for edited voice/text drafts, attaching a voice label only for rendering. Preserve Enter/IME behavior, busy guards, retry text, and old free-chat mode.
  - Add quick-lesson cards/controls with default `order-food`, start through `/practice-sessions`, render `progress`, disable after completion, and expose fixed practice sentence/“luyện lại bài”. Keep custom settings separate and do not restore an active session after reload.
  - Add an accessible translation checkbox/status and localStorage preference with try/catch. Send the effective value on API requests and render server-provided fields with `textContent` only.
  - Add separate local timestamps for transcript received, reply rendered, and audio playing; keep UI usable when mic/Whisper/TTS/Google is unavailable.

- [ ] **Step 4: Run frontend tests and syntax checks**
  - Run `node --test tests/test_frontend.js`, `node --check static/app.js`, and `pytest -q tests/test_frontend.py`.
  - Expected: all frontend tests pass, JavaScript parses, and static HTML contract tests pass.

- [ ] **Step 5: Run the full automated suite**
  - Run `pytest -q` and `node --test tests/test_frontend.js`.
  - Expected: backend and frontend suites pass together.

### Task 5: Document the MVP test protocol and verify the real app

**Files:**
- Create: `docs/mvp-user-test.md` — five-person learner test script and note template.
- Modify: `README.md` — quick lessons, transcript approval, translation toggle, and verification commands.
- Modify: `TEST_RESULTS.md` — dated automated/browser results and explicit physical-mic limitation or evidence.
- Test: real app at `http://127.0.0.1:8000` using the project run workflow.

**Interfaces:**
- Consumes: all endpoints/UI from Tasks 1–4 and the existing local service setup.
- Produces: reproducible QA instructions, honest test evidence, and a go/no-go checklist without inventing learner-study results.

- [ ] **Step 1: Add the learner test protocol**
  - Define one 5-turn task per quick lesson, the exact neutral facilitator prompt, what to record (completion, time, confusion, desired retry sentence), and the privacy rule not to collect audio or private sentences.
  - Include a small Markdown results table with participant pseudonym, lesson, completed unaided, time, blocker, and desired retry sentence.

- [ ] **Step 2: Run static and automated verification**
  - Run `pytest -q`, `node --test tests/test_frontend.js`, `node --check static/app.js`, `python3 -m compileall -q server.py tutor.py speech.py translation.py tests`, `bash -n scripts/run.sh`, and `git diff --check`.
  - Expected: all commands succeed; record exact totals and any skipped browser/mic checks.

- [ ] **Step 3: Run browser smoke checks**
  - Start the app through the project run workflow; verify desktop and 390px layouts, default quick lesson, keyboard 5-turn completion, translation off/on, denied mic fallback, TTS failure fallback, and reload behavior.
  - If a physical microphone is available, complete one real mic lesson; otherwise record only fixture/automation evidence and state that physical-mic acceptance remains open.

- [ ] **Step 4: Update verification results and report remaining acceptance work**
  - Add dates, commands, service configuration, screenshots/observations, and failures to `TEST_RESULTS.md` without claiming the five-person target unless it was actually run.
  - End with a concise MVP status: automated pass/fail, browser pass/fail, physical microphone tested/not tested, and learner study pending/complete.

---

## Self-review coverage

- The approved-transcript requirement is implemented and tested in Task 2 and Task 4.
- Lesson presets, five-turn progress, completion lock, retry semantics, concurrency, and fixed practice sentences are covered by Task 1 and Task 4.
- Translation default-off, request override, environment override, privacy payload, and graceful failure are covered by Task 3 and Task 4.
- Desktop/mobile smoke, audio fallback, and physical microphone evidence are covered by Task 5.
- No database, auth, public deployment, pronunciation grading, streaming, or new dependency is introduced.
