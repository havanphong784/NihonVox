# Kết quả kiểm thử — 20/11/2026

## Tự động sau khi thêm voice conversation

- `.venv/bin/pytest -q tests/test_speech.py tests/test_api.py tests/test_rules.py`: **91 targeted tests passed**; full pytest result **92 passed** (includes the Node wrapper).
- `node --test tests/test_frontend.js`: **25 passed**.
- `node --check static/app.js`: đạt.
- `python3 -m compileall -q server.py speech.py tests`: đạt.
- `bash -n scripts/run.sh`: đạt.
- `uv pip check --python .venv/bin/python`: `All installed packages are compatible`.

Backend test coverage mới:

- Whisper segment join, `language="ja"`, `task="transcribe"`, VAD và `beam_size=5`.
- Audio rỗng, suffix/MIME không hỗ trợ, upload quá giới hạn.
- Temporary recording directory/file cleanup sau thành công và exception.
- `/voice-chat` transcript → cùng session history → Ollama → VOICEVOX.
- Whisper unavailable nhưng typed chat vẫn chạy.
- No-speech/decoder failure không gọi Ollama hoặc VOICEVOX.
- Timeout speech trả 504.
- Chunked multipart body quá lớn bị chặn trước multipart parser.
- Health có `speech_model`.

Frontend test coverage mới:

- Microphone chỉ được xin quyền sau click `Nói`.
- Toggle `Nói`/`Dừng`, elapsed timer, upload multipart và session ID.
- Transcript được render trước reply bằng `textContent`.
- Permission denied, browser không hỗ trợ MediaRecorder, zero chunks, recorder error.
- Giải phóng microphone tracks khi stop/clear.
- Text composer vẫn dùng được khi voice lỗi.

## Kiểm thử end-to-end thật bằng model local

- Health thực: `{"status":"ok","ollama":true,"model":true,"voicevox":true,"speech_model":true}`.
- Tạo câu audio tiếng Nhật `今日はいい天気ですね。` bằng VOICEVOX thật, speaker 1; audio PCM mono 24 kHz, 16-bit, 1,99 giây.
- Gửi WAV qua `POST /voice-chat`; Whisper `small` CPU int8 trả `今日は良い天気ですね`; Ollama thật trả `はい、とても気持ちの良い日ですね`; VOICEVOX tạo WAV thật; HTTP 200 trong khoảng 10,78 giây; `source=ollama`, `error_audio=null`.
- Xóa session smoke-test sau khi xác minh.
- Browser UI đã kiểm tra tại desktop 1440×900 và mobile 390×844; cổng 8000 hiển thị cả Ollama, VOICEVOX và Whisper local Online; không tràn ngang.
- Test review fix: recorder lỗi không upload phần audio dở; sự kiện `stop` trễ từ recorder cũ không được phép dừng recorder mới.
- Thử model decoder khi PyAV 19 còn cài và bắt được lỗi `av.open(..., metadata_errors=...)`; khóa `av>=12,<19`, cập nhật đến PyAV 18.1.0 và test decode WAV thật đạt.

Đây là end-to-end backend với lời nói tổng hợp thật; chưa thực hiện được cuộc nói microphone vật lý trực tiếp trong browser automation. Unit tests dùng `MediaRecorder`, `getUserMedia`, `FormData` giả lập; backend dùng transcriber giả lập để không tải model trong test.

VOICEVOX thật tại `127.0.0.1:50021` trước đó offline; audio fixture beep đã kiểm tra playback nhưng không phải giọng VOICEVOX. Ollama thật đã được kiểm tra ở MVP trước và vẫn là upstream được giữ nguyên.

Để kiểm tra end-to-end thật trên máy có microphone:

```bash
cd ~/japanese-voice-assistant
./scripts/run.sh
# mở http://127.0.0.1:8000
# bấm Nói → nói tiếng Nhật → bấm Dừng
```

Lần đầu có thể mất thời gian tải model `small`. Nếu máy yếu, thử `WHISPER_MODEL=tiny ./scripts/run.sh`. Kiểm tra `speech_model` trong `/health` trước khi thử microphone. Nếu VOICEVOX offline, transcript và text reply vẫn hiển thị nhưng không có audio.
