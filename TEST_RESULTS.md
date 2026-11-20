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

## Thiết lập học tập — kiểm chứng phiên bản mới

- Baseline trước thay đổi: 92 pytest đạt.
- Sau thêm thiết lập: 117 pytest đạt (gồm wrapper chạy Node), 31 test JavaScript đạt ở lượt trước review.
- `/practice-sessions` thực: N5/Katakana/restaurant và N2/Kanji/work đều HTTP 201; trả UUID buổi học riêng, lời mở đầu và gợi ý tùy chọn.
- N5 mở đầu mẫu: `こんにちは！今日はカフェに行きたいですか？`; bài luyện `"コーヒー" nghĩa là gì?` → `Cà phê`.
- N2 mở đầu mẫu: `今日は仕事でどんなことがありましたか？`. Đây vẫn là câu khá đơn giản; đã truyền độ khó nhưng chưa thể đảm bảo model luôn đạt chất lượng N2.
- Lượt gõ và lượt WAV tiếng Nhật qua Whisper local đều HTTP 200, cùng session; VOICEVOX thật tạo WAV RIFF lần lượt 153132 và 245292 byte trong smoke-test. Mẫu input voice là audio VOICEVOX từ lần trước, không phải lời nói microphone trực tiếp của người dùng trong phiên này.
- Thử thật bắt được cấu hình model `stop` ở dấu câu và `num_predict=32` cắt JSON. Đã thêm regression test và ghi đè riêng cho buổi học: `stop=[]`, `num_predict=768`, `num_ctx=4096`; không sửa Modelfile hoặc provider.
- Trình duyệt thực: chọn N5/Katakana/quán cà phê, mở buổi, có 1 tin trợ lý mở đầu; đổi select chủ đề sang công việc chưa bấm bắt đầu thì nhãn active vẫn là quán cà phê. Lượt gõ tiếp tục buổi cũ; gợi ý/đáp án ban đầu đều đóng. Đã mở nội dung để xem và chụp desktop/mobile 390px, không chồng lấn hoặc tràn ngang trong ảnh.
- Giới hạn quan sát: model đôi lúc trả lời không sát yêu cầu (gọi cà phê nhưng gợi ý trà; có câu hỏi nghĩa nhưng trả phiên âm). Bộ lọc kiểm tra cấu trúc và hệ chữ, không bảo đảm ngữ nghĩa đúng. Cần coi phản hồi là gợi ý học, không phải đáp án chuẩn tuyệt đối.
- Sau khi tab đầu bị đóng, đã mở tab kiểm thử mới và reload thực: lựa chọn N5/Katakana/work được giữ; nhãn active là chưa có buổi luyện và số tin nhắn 0. Không âm thầm khôi phục session cũ.

### Sau review và bàn giao

- Review độc lập xác nhận hai lỗi quan trọng. Đã thêm test đỏ rồi sửa: JSON lồng trong `reply` bị từ chối trước TTS; xóa buổi luyện cũng xóa ngữ cảnh chat tự do sắp được khôi phục.
- API regression xác nhận reply dạng JSON không gọi `/audio_query` hoặc `/synthesis`; session hết hạn trả 410, không dùng rule generic.
- Kết quả cuối: **122 pytest passed**, **32 Node tests passed**, JavaScript syntax/Python compile và `git diff --check` đạt.
- Đã dừng app test riêng tại 18000, khởi động lại app mặc định với bản code mới tại **http://127.0.0.1:8000**. Health thực có cả 4 service/model flags true; browser hiển thị đủ **5 trình độ, 3 hệ chữ, 12 chủ đề**, không tràn ngang. Không dừng Ollama hoặc VOICEVOX.
- Chưa tạo commit/push cho thay đổi thiết lập học tập này.

## Google dịch lời đáp Nhật → Việt — 20/11/2026

### Tự động

- Baseline của commit `ae3ca36`: 122 pytest passed, 32 Node passed.
- Sau tích hợp dịch: **148 pytest passed** (gồm wrapper Node), **35 Node passed** trước lượt review cuối.
- Adapter được kiểm thử RED→GREEN với HTTP transport giả lập, không gọi Google trong automated suite: nối segment, request chỉ chứa reply, cache hit/TTL/LRU, lỗi mạng, hard deadline, 429/503/redirect, response rỗng/hỏng/quá lớn, disable, cancellation.
- API tích hợp: rule, opener, lượt gõ tutor và lượt nói tutor chỉ gửi `reply` cuối cùng đi dịch; input/transcript/góp ý/bài tập không vào payload Google; query VOICEVOX vẫn đúng câu Nhật. Health không gọi Google. Env tắt dịch không gửi request. Tạo audio và dịch khởi chạy song song.
- Google offline/timeout/429/JSON hỏng: vẫn HTTP 201 cho opener, text + WAV + learning giữ nguyên, thêm notice dịch. Tests không thực hiện rate-limit abuse với dịch vụ thật.
- Renderer: bản dịch là textContent với lang=vi ngay dưới câu Nhật, kể cả nội dung giống HTML; opener/lượt nói dùng chung renderer; lỗi dịch không khóa replay hay learning.

### Kiểm chứng dịch vụ thật

- Google endpoint không key đã trả HTTP 200 cho câu thử `今日は何を飲みますか？` → `Hôm nay bạn uống gì?`.
- App test riêng cổng 18000 có health local `status=ok`, Ollama/model/VOICEVOX/Whisper đều true.
- Rule `お茶`: HTTP 200; reply `ホットとアイス、どちらにしますか？`, translation `Bạn muốn nó nóng hay đá?`, WAV thật 156204 byte, error_translation=null.
- Opener N5/Katakana/restaurant: HTTP 201; reply `こんにちは！今日はカフェに行きたいですか？`, translation `Xin chào! Hôm nay bạn có muốn đi cafe không?`, WAV 179756 byte, learning vẫn riêng.
- Lượt gõ: HTTP 200 với `はい、お茶でもいかがでしょうか？` → `Ừ, uống trà nhé?`, WAV 153132 byte.
- Lượt voice: WAV mẫu do VOICEVOX tạo từ phiên trước → Whisper thật cho transcript `今日は良い天気ですね`; reply `そうですか、とても気持ちいいですね！` → `Tôi thấy rồi, cảm giác thật tuyệt!`; HTTP 200, WAV 156716 byte. Không thu lời nói người thật mới trong lần test này.
- Browser thật: DOM xác nhận `.message-translation` ngay sau `.message-text`, label Google và lang vi; desktop 1440px/mobile 390px đã xem screenshot; mobile scrollWidth=innerWidth, không tràn ngang.
- Mở buổi học trong browser: `こんにちは！あなたの趣味は何ですか？` → `Xin chào! Sở thích của bạn là gì?`; native audio readyState=4, có event play/ended; bấm replay tạo play lần hai. Bản dịch vẫn là text, không được đọc.

### Giới hạn và quyền riêng tư

- Dịch vụ Google không chính thức có thể bị thay đổi/chặn; không cam kết chính xác tuyệt đối hoặc miễn phí vô hạn.
- Chỉ lời đáp AI rời máy; nếu AI nhắc lại thông tin người học thì phần nhắc lại nằm trong reply cũng được gửi. Không đưa dữ liệu nhạy cảm vào cuộc hội thoại khi bật dịch.
- Có thể tắt bằng `TRANSLATION_ENABLED=0`, cache RAM tối đa 256 câu trong 1 giờ; không lưu bản dịch ra file.

### URL mặc định sau triển khai dịch

- Đã restart app mặc định ở cổng 8000 và dừng app thử riêng 18000; không dừng Ollama hoặc VOICEVOX.
- `/health` tại 8000 trả status=ok. `/chat` smoke-test thật trả `Bạn muốn nó nóng hay đá?` ngay dưới reply rule tương ứng, `error_translation=null` và WAV thật. Đã xóa session smoke-test sau khi kiểm tra.
- Browser tại `http://127.0.0.1:8000/` đã tải thông báo Google/ngoài máy, các trạng thái local Online và không tràn ngang.
- Commit `ae3ca36` chỉ chứa phần thiết lập học tập trước đó; thay đổi dịch Google hiện vẫn chưa commit.
- Kiểm tra cache với Google thật: câu mẫu `今日は何を飲みますか？` nhận `Hôm nay bạn uống gì?` trong khoảng 0,27 giây; gọi lại cùng câu trả ngay từ RAM, tổng số request Google vẫn là 1. Adapter `enabled=False` không tạo thêm request.
