# Google Reply Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task with test-driven development. User explicitly selected inline implementation; no further approval gate. Do not commit or push without request.

**Goal:** Show a Google Japanese-to-Vietnamese translation immediately under each AI reply without breaking local voice chat when Google fails.
**Architecture:** Add a bounded, cached translation adapter using the existing httpx client. In the common reply pipeline, translate only the final Japanese reply concurrently with speech synthesis; additive response fields feed a safe shared browser renderer.
**Tech Stack:** Existing Python/FastAPI/httpx/Pydantic, vanilla JavaScript/CSS, pytest and node:test; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-11-20-google-translation-design.md`

## Global Constraints
- Google endpoint is unofficial and requires no key: `https://translate.googleapis.com/translate_a/single`; `client=gtx`, `sl=ja`, `tl=vi`, `dt=t`, `q=reply` only.
- Never send input, transcript, history, correction, exercise, audio or identifying headers to Google; cloud translation is explicitly authorized for final AI reply only.
- Hard total deadline 6 seconds, network timeout 5 seconds; maximum response 64 KiB; 256 successful cache entries with 3600-second TTL in RAM. Bound output text to 8000 characters and reject empty/malformed responses.
- `TRANSLATION_ENABLED=0` disables translation and makes no Google requests; default enabled. No API key, billing, dependency or persistent cache.
- New response fields: `translation: str | None`, `error_translation: str | None`. Existing response fields/rules/two-sentence tutor behavior/history remain intact.
- Translation failure returns `(None, short Vietnamese notice)`, never changes HTTP chat success or audio. Cache successes only. Cancellation propagates.
- Render text with `textContent`, `lang=vi`, directly below `.message-text` and before playback/feedback. Only Japanese reply reaches VOICEVOX.

## Review Focus
1. Google blocked/429, hung request, oversized or malformed response must not turn successful chat into an exception (Task 1).
2. Failed translations must not poison cache; expired entries and capacity eviction must prevent unlimited retention (Task 1).
3. Actual outbound `q` must exclude learner text, history, correction and exercises even in voice/structured tutor flows (Task 2).
4. A translation containing markup must remain text, and a missing translation must not disable replay or learning UI (Task 2).
5. Users must see that translation leaves the machine and can disable it without losing local chat (Tasks 1–3).

## Task 1: Google adapter
**Files:** Create `translation.py`, `tests/test_translation.py`.
**Interfaces:** `GoogleTranslator(client: httpx.AsyncClient, *, enabled=True, timeout=6.0, cache_size=256, cache_ttl=3600.0)`; `async def translate(self, reply: str) -> tuple[str | None, str | None]`.
- [ ] Write tests executing adapter with MockTransport: translated segments joined in order; literal q/ja/vi fields; hit avoids second request; TTL expiry and oldest-entry eviction; non-200/429, malformed JSON, nonstring and empty segments return a notice; 64 KiB limit; network exception and hard deadline; retry succeeds after an uncached failure; disabled makes zero calls.
- [ ] Run `.venv/bin/pytest -q tests/test_translation.py`; expected failures for missing adapter.
- [ ] Implement streamed GET with bounded body and JSON schema checks; validate complete segment list, join translated segments; cache only successful output with monotonic expiration and bounded LRU; no payload logging or remote fallback.
- [ ] Run `.venv/bin/pytest -q tests/test_translation.py`; all pass.

## Task 2: Common reply/API and browser rendering
**Files:** Modify `server.py`, `static/app.js`, `static/style.css`, `static/index.html`, `tests/test_api.py`, `tests/test_practice_api.py`, `tests/test_frontend.js`.
**Interfaces:** Settings adds `translation_enabled=True`, env `TRANSLATION_ENABLED`; ChatOutput adds `translation`, `error_translation`; lifespan creates app.state.translator with shared client. `play_reply` concurrently awaits translator and existing audio-lock-protected synthesis; sets both new fields explicitly, including null when disabled. `/voice-chat` preserves additive fields. Frontend `renderReply` inserts `.message-translation` below reply; uses `.translation-notice` for failures, no extra Google call in frontend.
- [ ] Add Google branch to the API MockTransport fixture (do not access real internet in tests). Write tests: rule, practice opener, typed tutor and voice tutor each translate final reply only; TTS request remains Japanese; offline/429/malformed translation leaves status 200/201, reply and WAV valid; disabled emits no request; health emits no request. Update exact response-key test to expect additive fields (not deletion/renaming of old fields).
- [ ] Run focused API tests; expected red for missing response fields and outbound requests.
- [ ] Implement Settings/env adapter injection and parallel translation/speech. Retain existing audio lock only around synthesis, not cache/network translation. Set no-store headers for translated chat responses; do not put any key or external endpoint in JS.
- [ ] Extend node tests: normal translated response shown directly below Japanese reply; translated hostile HTML remains text with lang vi; new opener and voice responses render it; offline translation notice does not disable replay or learning; absent fields remain compatible with fixtures.
- [ ] Run `node --test tests/test_frontend.js`; observe red, then implement safe translation rendering using shared renderer and minimal existing-theme styles. Add visible privacy note that Google receives AI reply text; keep responsive UI and keyboard behavior.
- [ ] Run `.venv/bin/pytest -q && node --test tests/test_frontend.js && node --check static/app.js`; all pass.

## Task 3: Live verification and documentation
**Files:** `README.md`, `TEST_RESULTS.md`; update plan ledger.
- [ ] Document external data flow, unofficial/no guarantee status, in-memory cache lifetime, hard timeout, env disable, new response fields, unchanged Japanese TTS; correct existing blanket local-only claims.
- [ ] Start an isolated app test port without stopping user services; test Google translation via actual rule and lesson responses plus WAV. Verify no-key error fallback with MockTransport and real normal call; never induce actual rate limits.
- [ ] Browser: observe Japanese + Vietnamese underneath, opener/voice behavior, playback and feedback compatibility; check desktop/mobile no overflow and inspect screenshot. Distinguish actual mic from fixture.
- [ ] Run full pytest, Node, syntax checks, `git diff --check`, dependency check. One fresh bounded final reviewer per executing-plans; fix confirmed Important issues with red/green tests, record any deferred minors. Restart only task-owned app for final URL and report exact evidence/limitations; leave changes uncommitted.
