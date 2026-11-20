# Luyện hội thoại tiếng Nhật — local MVP

Ứng dụng web chạy cục bộ: nhập văn bản → rule hoặc Ollama → một câu trả lời tiếng Nhật → VOICEVOX → phát WAV. Không React/Vue, không bundler, không Docker, không dùng microphone hay dịch vụ đám mây. Có thể dùng Voxtype để nhập vào ô văn bản như bàn phím.

## Chạy nhanh

Yêu cầu Python **3.10+**, Ollama và VOICEVOX cài sẵn. Python 3.12 đã được dùng để kiểm thử dự án này.

```bash
cd ~/japanese-voice-assistant
./scripts/run.sh
```

Mở **http://127.0.0.1:8000**. Dừng bằng `Ctrl+C` trong terminal đang chạy server.

`run.sh` tự tạo `.venv` và cài `requirements.txt` nếu thiếu thư viện. Nếu có `uv`, script dùng nó; nếu không, script dùng `python3 -m venv` và pip. Không cài package vào Python hệ thống.

Cài thủ công nếu muốn:

```bash
cd ~/japanese-voice-assistant
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./scripts/run.sh
```

Nếu môi trường được tạo bằng `uv` không có pip:

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

Ứng dụng chỉ bind loopback theo mặc định, dùng **một worker** vì lịch sử lưu trong bộ nhớ. Không thêm `--workers` khác 1. Không cần reload server khi chỉ thay đổi frontend; tải lại trang để lấy JS/CSS mới.

## Cấu hình

Biến môi trường được đọc khi khởi động; không tự đọc file `.env`.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Địa chỉ Ollama |
| `OLLAMA_MODEL` | `japanese-tutor` | Tên model; health chấp nhận alias `japanese-tutor:latest` |
| `VOICEVOX_URL` | `http://127.0.0.1:50021` | Địa chỉ VOICEVOX |
| `VOICEVOX_SPEAKER_ID` | `1` | Speaker ID |
| `OLLAMA_TIMEOUT` | `90` | Timeout mỗi request Ollama, giây |
| `VOICEVOX_TIMEOUT` | `20` | Timeout mỗi request VOICEVOX, giây |
| `AUDIO_DIR` | `<project>/runtime/audio` | Nơi lưu WAV |
| `HOST` | `127.0.0.1` | Host Uvicorn |
| `PORT` | `8000` | Port Uvicorn |

Ví dụ:

```bash
VOICEVOX_URL=http://127.0.0.1:50021 \
VOICEVOX_SPEAKER_ID=1 \
./scripts/run.sh
```

Không đổi `HOST` sang `0.0.0.0` trên mạng không tin cậy: MVP không có đăng nhập/TLS. Bố cục hỗ trợ mobile, nhưng mặc định chỉ máy cục bộ truy cập được. Có thể dùng chuyển tiếp SSH riêng nếu cần mở từ thiết bị khác.

## Cách sử dụng

- Nhập `お茶`, `おちゃ`, `コーヒー` hoặc `コーヒーをください` → `ホットとアイス、どちらにしますか？`.
- Nhập `アイス` hoặc `アイスで` → `かしこまりました。`.
- Rule khớp chính xác sau khi chuẩn hóa Unicode, bỏ khoảng trắng và dấu kết thúc câu; không khớp một phần câu dài.
- Nhập `今日はいい天気ですね。` để gọi model thật.
- Enter gửi; Shift+Enter xuống dòng. Enter khi đang gõ bằng IME không gửi nhầm.
- Nút gửi và xóa tạm khóa khi xử lý; câu nhập được giữ lại nếu gửi lỗi.
- Nhãn nhỏ `rule`/`ollama` cho biết nguồn; thời gian phản hồi gồm cả tạo audio.
- Có audio thì trình duyệt thử tự phát. Nếu bị chặn, bấm `Phát`; không coi đây là lỗi nghiêm trọng.
- `Phát lại` phát câu trả lời gần nhất nếu câu đó có audio. Lượt gửi thất bại không làm mất nút phát lại của câu trả lời trước.
- `Xóa hội thoại` gọi DELETE rồi mới xóa giao diện; nếu DELETE lỗi, giữ hội thoại trên màn hình.
- `Kiểm tra hệ thống` kiểm tra lại các dịch vụ; kiểm tra tự chạy khi mở trang.

### Session và giới hạn

Lần mở đầu tạo giá trị session `default` trong localStorage khóa `japanese-voice-session`, dùng lại cho các lượt tiếp theo. Vì yêu cầu nút xóa gọi `/sessions/default`, giao diện mặc định dùng tên này thay vì UUID ngẫu nhiên. Có thể đặt session ID khác trong localStorage/API; khi đó nút xóa dùng đúng ID đã lưu. Các tab dùng cùng ID sẽ chia sẻ lịch sử backend. Nếu localStorage bị chặn, trang vẫn dùng `default`.

Mỗi session giữ tối đa **10 cặp user/assistant gần nhất**, có cả các lượt rule; lượt lỗi Ollama không ghi vào lịch sử. Khóa theo session giữ đúng thứ tự khi có nhiều request hoặc thao tác xóa đang chờ. Tối đa 128 session, hết hạn sau 6 giờ không sử dụng. Đạt giới hạn trả 503, có thể DELETE session cũ để giải phóng. Khởi động lại server sẽ mất lịch sử. Nội dung hội thoại không ghi vào file; request log chỉ chứa đường dẫn/trạng thái, không log câu nhập.

Reload trang không tải lại tin nhắn cũ lên giao diện, nhưng backend vẫn nhớ lịch sử session cho đến khi xóa/hết hạn/restart. MVP chưa có API tải lịch sử.

### Ollama và giới hạn câu trả lời

Mỗi lần gọi `/api/chat` đều gửi `think: false`, `stream: false` và model đã cấu hình, kèm system prompt tiếng Nhật và lịch sử giới hạn. Rule không gọi Ollama.

Backend bỏ block `<think>`, chọn câu tiếng Nhật đầu tiên và dừng sau dấu đầu tiên trong `。！？?!`. Không cắt giữa câu theo số ký tự. Nếu không có dấu kết thúc, giữ nguyên câu; nếu câu quá dài hoặc không có nội dung tiếng Nhật, trả lỗi 502 thay vì đọc một mảnh câu. Không gọi VOICEVOX cho reply rỗng/không hợp lệ.

### VOICEVOX và WAV

Backend thử `GET /audio_query?speaker=...&text=...` theo yêu cầu. Nếu engine trả **405 Method Not Allowed**, tự thử `POST /audio_query` với cùng query parameters để tương thích engine chỉ nhận POST. Sau đó POST `/synthesis?speaker=...` với nguyên JSON nhận được.

WAV được kiểm tra bằng bộ đọc WAV của Python, lưu với tên UUID 32 ký tự hex, không lấy tên từ text. `/audio/{filename}` chỉ chấp nhận mẫu UUID `.wav` trong thư mục audio, từ chối symlink và traversal. Không expose thư mục runtime; chỉ các asset giao diện được phục vụ dưới /static.

Giữ tối đa 200 WAV và xóa file quá 24 giờ lúc khởi động hoặc tạo WAV mới; audio cũ có thể hết hạn, cần gửi lại câu. `Xóa hội thoại` xóa lịch sử và dừng audio trên trang, **không xóa ngay WAV đã tạo**. WAV nằm cục bộ đến lúc dọn tự động hoặc người dùng xóa thư mục runtime khi đã dừng server.

VOICEVOX offline, timeout, WAV hỏng hoặc lỗi ghi file: `/chat` vẫn trả 200 với text, `audio_url: null`, `error_audio` tiếng Việt. Không làm server dừng.

## API và curl

```bash
curl -s http://127.0.0.1:8000/health

curl -s http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"お茶","session_id":"default"}'

curl -s http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"今日はいい天気ですね。","session_id":"default"}'

curl -s -X DELETE http://127.0.0.1:8000/sessions/default
```

| Endpoint | Hành vi |
|---|---|
| `GET /` | Trả giao diện |
| `GET /health` | JSON `status`, `ollama`, `model`, `voicevox`; luôn HTTP 200, `degraded` nếu thiếu dịch vụ |
| `POST /chat` | Trả `reply`, `audio_url`, `source`, `session_id`, `error_audio` |
| `DELETE /sessions/{session_id}` | Xóa lịch sử, idempotent |
| `GET /audio/{filename}` | Chỉ phục vụ WAV UUID hợp lệ trong thư mục audio |

Input: 1–2000 ký tự sau trim. Session: 1–64 ký tự ASCII chữ/số/`_`/`-`. Lỗi JSON/input trả 422; Ollama offline/model thiếu trả 503; timeout Ollama trả 504; upstream rỗng/hỏng trả 502; lỗi server trả JSON 500 không lộ chi tiết nội bộ. Lỗi audio không biến thành lỗi hội thoại. Health dùng timeout 3 giây và kiểm tra hai dịch vụ song song. Frontend dùng toàn bộ relative URL và `textContent`, không render HTML model. POST/DELETE có Origin khác server bị từ chối; không bật CORS.

## Kiểm thử

```bash
cd ~/japanese-voice-assistant
.venv/bin/python -m pytest -q
# Hoặc sau khi kích hoạt .venv:
source .venv/bin/activate
pytest -q
```

Test backend không cần Ollama/VOICEVOX thật: chỉ giả lập HTTP transport của dịch vụ ngoài, vẫn chạy toàn bộ route và xử lý file thật. Bao phủ rule, `think: false`, source, câu đầu, history/reset/concurrency, timeout/offline, reply rỗng, WAV hỏng, traversal/symlink, giới hạn tài nguyên và lỗi server.

Node **chỉ là tùy chọn để chạy test JavaScript**, không cần để chạy ứng dụng. Khi có Node, pytest tự chạy thêm test hành vi frontend bằng built-in `node:test`; nếu không, riêng test này được đánh dấu skip, không che giấu.

```bash
node --test tests/test_frontend.js
```

Các test JS chạy file `app.js` thật trong DOM adapter tối thiểu để kiểm tra Enter/IME, tránh gửi trùng, textContent/XSS, localStorage/autoplay bị chặn, timeout, reset, replay và lỗi mạng. Kiểm thử trình duyệt thật đã được thực hiện riêng; xem [TEST_RESULTS.md](TEST_RESULTS.md).

### Lặp lại kiểm thử WAV nếu VOICEVOX đang offline

Terminal 1 — dịch vụ giả lập tạo **âm beep 0,4 giây, không phải giọng VOICEVOX**:

```bash
cd ~/japanese-voice-assistant
.venv/bin/python -m uvicorn --app-dir tests stub_services:app \
  --host 127.0.0.1 --port 18021
```

Terminal 2 — app riêng, vẫn gọi Ollama thật:

```bash
cd ~/japanese-voice-assistant
PORT=18000 VOICEVOX_URL=http://127.0.0.1:18021 \
AUDIO_DIR="$PWD/runtime/integration-audio" ./scripts/run.sh
```

Mở http://127.0.0.1:18000, nhập `お茶`, kiểm tra `source=rule`, `Phát`, `Phát lại` và file `/audio/<uuid>.wav`. Không đổi cấu hình mặc định của app ở 8000. Dừng hai process bằng Ctrl+C sau khi thử.

Kiểm thử offline không cần tắt dịch vụ của máy:

```bash
PORT=18001 OLLAMA_URL=http://127.0.0.1:11999 \
VOICEVOX_URL=http://127.0.0.1:11998 \
AUDIO_DIR="$PWD/runtime/offline-audio" ./scripts/run.sh
```

Điều kiện: các cổng giả lập offline phải chưa có process lắng nghe. App ở http://127.0.0.1:18001 sẽ báo dịch vụ offline; câu rule vẫn có text, câu ngoài rule trả lỗi Ollama rõ ràng.

## Cấu trúc

```text
japanese-voice-assistant/
├── server.py
├── requirements.txt
├── pytest.ini
├── README.md
├── TEST_RESULTS.md
├── .gitignore
├── scripts/run.sh
├── static/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── tests/
│   ├── test_rules.py
│   ├── test_api.py
│   ├── test_frontend.py
│   ├── test_frontend.js
│   └── stub_services.py
├── docs/superpowers/plans/2026-11-20-mvp.md
└── runtime/                 # Sinh khi chạy, không đưa vào git
```

## Giới hạn MVP

Chưa có thu âm/microphone, nhận dạng giọng nói, lưu database, đồng bộ lịch sử UI sau reload, đăng nhập, nhiều worker hay triển khai public. Chất lượng câu trả lời phụ thuộc model Ollama. Cần VOICEVOX engine thật đang chạy để nghe giọng tổng hợp tiếng Nhật; fixture test không thay thế engine.

## Trò chuyện trực tiếp bằng microphone

MVP hiện hỗ trợ luồng:

```text
Bấm Nói → nói tiếng Nhật → bấm Dừng
→ faster-whisper local tạo transcript
→ Ollama trả lời theo session
→ VOICEVOX tạo WAV → trình duyệt phát
```

Nút microphone chỉ xin quyền sau khi người dùng bấm **Nói**. Khi đang ghi, nút đổi thành **Dừng** và hiển thị thời gian. Sau khi dừng, transcript được tự gửi; giao diện hiển thị transcript với nhãn `giọng nói`, sau đó hiển thị câu trả lời của trợ lý. Ô nhập văn bản vẫn luôn là fallback.

### Cài speech-to-text

`requirements.txt` đã có `faster-whisper` và `python-multipart`. Cài lại môi trường:

```bash
cd ~/japanese-voice-assistant
uv pip install --python .venv/bin/python -r requirements.txt
# hoặc:
.venv/bin/python -m pip install -r requirements.txt
```

Lần khởi động đầu tiên, `faster-whisper` tải model Whisper từ model registry vào cache local. Mặc định:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `WHISPER_MODEL` | `small` | Chất lượng/độ nặng model |
| `WHISPER_DEVICE` | `cpu` | `cpu` hoặc thiết bị tương thích |
| `WHISPER_COMPUTE_TYPE` | `int8` | Kiểu tính toán phù hợp CPU |
| `WHISPER_DOWNLOAD_ROOT` | `runtime/whisper` | Cache model local |
| `MAX_RECORDING_BYTES` | `10485760` | Giới hạn upload 10 MiB |
| `TRANSCRIPTION_TIMEOUT` | `120` | Timeout nhận dạng, giây |

Nếu model không tải được hoặc thiếu dependency, server vẫn khởi động và `/chat` bằng text vẫn hoạt động. `/health` trả thêm `speech_model: false`; giao diện báo lỗi microphone nhưng không khóa ô nhập.

`faster-whisper` nhận dạng v1 chỉ ép `language="ja"`, có VAD và `beam_size=5`. Có thể dùng model nhỏ hơn trên máy yếu:

```bash
WHISPER_MODEL=tiny ./scripts/run.sh
```

Chất lượng transcript phụ thuộc microphone, tiếng ồn, model và CPU. Bản ghi chỉ được giữ trong RAM/request và một file tạm ngắn hạn cần thiết cho decoder; file tạm được xóa sau khi Whisper hoàn tất. Không lưu audio người học vào `runtime/audio` và không ghi transcript vào log.

### API microphone

```bash
curl -s \
  -F 'audio=@sample.wav;type=audio/wav' \
  -F 'session_id=default' \
  http://127.0.0.1:8000/voice-chat
```

Response thành công có dạng:

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

Định dạng browser ưu tiên là `audio/webm;codecs=opus`, sau đó `audio/webm`, `audio/ogg;codecs=opus`, `audio/mp4`. Server giới hạn toàn bộ multipart envelope ở mức audio 10 MiB cộng 64 KiB và không chấp nhận upload lớn trước khi parser multipart chạy. Audio rỗng/không hỗ trợ trả 422; model speech chưa sẵn sàng trả 503; timeout trả 504; lỗi decoder trả 502. Trình duyệt dành tối đa 300 giây cho voice request (120 giây Whisper + tối đa 90 giây Ollama + các timeout VOICEVOX). Lỗi VOICEVOX vẫn trả transcript/reply dạng text.

### Quyền microphone

`http://127.0.0.1:8000` là loopback origin được trình duyệt xem là secure context cho `getUserMedia`. Nếu trình duyệt từ chối quyền, vào phần Site settings của origin và cho phép Microphone, sau đó tải lại trang hoặc bấm lại `Nói`. Không cấp quyền tự động khi mở trang. Nếu browser không có `MediaRecorder` hoặc không tìm thấy microphone, dùng ô nhập text/Voxtype.

**Lưu ý tương thích:** `requirements.txt` giới hạn `av<19`. `faster-whisper` 1.x hiện gọi `av.open(..., metadata_errors=...)`, API đã bị loại bỏ trong PyAV 19; giữ giới hạn này để decoder không lỗi lúc nhận dạng. PyAV 18 đã được kiểm tra với WAV thật.

## Thiết lập buổi học: trình độ, chữ và chủ đề

Chọn **N5–N1**, **Hiragana / Katakana / Kanji** và một trong 12 chủ đề, rồi bấm **Bắt đầu luyện**. Mặc định N5 · Hiragana · Giao tiếp hằng ngày. Trợ lý mở đầu bằng câu hỏi/tình huống; các lượt nói và gõ sau đó dùng chung buổi học và lịch sử.

- Trình độ định hướng độ khó; không đảm bảo mỗi từ thuộc đúng danh mục JLPT chính thức.
- Hệ chữ chỉ áp dụng cho bài luyện riêng, **không ép lời thoại** sang toàn Hiragana hoặc Katakana.
- Mục **Gợi ý học tập** đóng mặc định. Mở để xem góp ý (khi cần) và bài luyện; đáp án nằm trong **Xem đáp án**. VOICEVOX chỉ đọc lời thoại, không đọc góp ý hoặc đáp án.
- Góp ý cho lượt nói dựa trên transcript, không phải chấm phát âm; model vẫn có thể nhận định sai.
- Trình duyệt chỉ lưu lựa chọn. Đổi select không thay đổi buổi hiện tại cho đến lần bấm bắt đầu tiếp theo. Nếu mở đầu thất bại, buổi cũ và audio còn nguyên. Tải lại trang giữ lựa chọn nhưng không tự khôi phục buổi/lịch sử cũ.
- Xóa hội thoại kết thúc buổi. Session hết hạn, đã xóa hoặc mất sau restart trả 410; bấm **Bắt đầu luyện** để mở buổi mới. Không tự chuyển request của buổi mất sang generic chat.
- Trước khi bắt đầu buổi, chat kiểu cũ vẫn hoạt động. Request cũ vẫn dùng rule và giới hạn một câu. Buổi học không dùng rule cố định, để cả những câu như `お茶` được trả lời theo chủ đề và trình độ.

### API buổi học

```bash
curl -s http://127.0.0.1:8000/practice-sessions \
  -H 'Content-Type: application/json' \
  -d '{"level":"N5","script":"katakana","topic":"restaurant"}'
```

HTTP 201 trả lời mở đầu với `session_id` mới dạng `practice-<uuid>`. Gửi ID đó trong `/chat` hoặc form `/voice-chat`. Có thêm trường tùy chọn:

```json
{
  "learning": {
    "correction": null,
    "exercise": {"prompt": "「コーヒー」 nghĩa là gì?", "answer": "Cà phê"}
  }
}
```

Các chủ đề: `daily`, `introductions`, `family`, `school`, `work`, `hobbies`, `restaurant`, `shopping`, `travel`, `weather`, `jlpt`, `free`. Giá trị ngoài danh sách trả 422 trước khi gọi model. Phần học không hợp lệ có thể bị bỏ qua mà vẫn giữ lời thoại; các trường này không được thêm vào API cũ nếu không có nội dung học.

Không đổi model/provider mặc định. Riêng request buổi học ghi đè `stop=[]`, `num_predict=768`, `num_ctx=4096` để cấu hình model local (vốn dừng ở dấu câu với 32 token) không cắt JSON. Không cần cài thư viện mới hoặc database.
