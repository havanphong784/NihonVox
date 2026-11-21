# NihonVox — Hoàn thiện MVP luyện nói

## Mục tiêu

Người Việt học tiếng Nhật sơ cấp có thể tự hoàn thành một bài hội thoại khoảng 5 phút, bằng mic hoặc bàn phím, và kết thúc với một câu cụ thể để luyện lại. Phạm vi phát hành tập trung vào ba bài N5–N4; giữ chat tự do và phần thiết lập N5–N1 hiện có. Năm phút là mục tiêu trải nghiệm, không phải bộ đếm giờ.

Giữ FastAPI, HTML/CSS/JS, Whisper và Ollama local, VOICEVOX; không thêm framework, tài khoản, database, khôi phục lịch sử, chấm phát âm hay triển khai public. Không đổi cấu hình model mặc định.

## Các hướng đã cân nhắc

- Giữ `/voice-chat` tự gửi rồi cho sửa: ít thay đổi hơn nhưng ngữ cảnh đã nhận câu sai; sửa và gửi lại còn có thể làm sai tiến độ bài.
- Tách nhận dạng khỏi gửi và mở rộng luồng luyện hiện có (**chọn**): thêm một lần xác nhận ở lượt nói, đổi lại người học kiểm soát được câu trước khi AI và lịch sử nhận nó. Dùng bài mẫu để định hướng model, nhưng dùng mã ứng dụng để đếm lượt và chốt bài.
- Viết một hệ hội thoại theo kịch bản cứng: dễ kiểm thử nội dung nhưng khó xử lý câu trả lời đúng theo cách diễn đạt khác, và phải duy trì luồng học riêng.

## Luồng học

```text
Bài nhanh: Gọi món (mặc định) / Tự giới thiệu / Hỏi đường
→ Bắt đầu luyện → [Mục tiêu] [Lượt 0/5] [Câu mở đầu]
→ Nói · Dừng → [Kiểm tra câu nhận dạng] [Thu lại] [Gửi]
  hoặc gõ → Gửi
→ Lượt 5/5 → [Hoàn thành] [Câu nên luyện lại] [Luyện lại bài]
```

- Ba bài mặc định: `order-food` (N5, `restaurant`, yêu cầu một món và trả lời câu hỏi tiếp theo), `introduce-yourself` (N5, `introductions`, giới thiệu và chia sẻ sở thích), `ask-directions` (N4, `travel`, hỏi đường và xác nhận chỉ dẫn đơn giản). Các bài dùng Hiragana cho phần luyện chữ, không đổi cách viết lời thoại. Mỗi bài định nghĩa một mục tiêu tiếng Việt, chỉ dẫn vai/ngữ cảnh tiếng Nhật cho Ollama và một câu mẫu Nhật–Việt được biên soạn sẵn. Câu mẫu không phải đánh giá phát âm hay kết luận AI về người học.
- Nút bắt đầu bài nhanh dùng mặc định Gọi món và không cần cấu hình trước. Giữ bộ chọn trình độ/chữ/chủ đề trong phần luyện tùy chỉnh; tùy chỉnh và chat tự do không giới hạn 5 lượt. Vẫn có thể chọn bài khác. Chuyển bài chỉ thay buổi hiển thị khi mở buổi mới thành công. Không tự khôi phục buổi sau reload.
- Lượt mở đầu không tính. **Mọi nội dung không rỗng được gửi thành công đều tính một lượt; không kiểm tra câu có ký tự Nhật và không chấm ngữ pháp.** Backend đếm các lượt có lời đáp tiếng Nhật hợp lệ dưới khóa session hiện có. Lỗi nhận dạng, gửi hỏng hoặc model trả lời không hợp lệ không tăng lượt và không ghi câu người học vào history; câu nháp vẫn được giữ để sửa/gửi lại mà không bị nhân đôi. Nếu câu Nhật đã hợp lệ nhưng TTS hoặc dịch lỗi, vẫn ghi lượt vào history và tăng tiến độ vì phần hội thoại đã thành công. Trả tiến độ cùng lời đáp. Sau lượt 5 hiển thị câu mẫu và nút luyện lại; khóa gửi/ghi cho buổi đó, nhưng vẫn có thể nghe lại, xóa hoặc bắt đầu buổi mới. Phía API từ chối lượt thêm bằng 409; hết hạn vẫn 410. Không chặn hoàn thành vì AI đánh giá người học chưa đạt mục tiêu.
- Mic: sau khi dừng, giải phóng mic như hiện tại và nhận dạng local. Transcript xuất hiện dưới dạng bản nháp có thể sửa trong ô nhập hiện có, có nhãn và nút thu lại. Không ghi đè bản nháp gõ dở: nút Nói không bắt đầu khi có bản nháp gõ chưa gửi; với bản nháp giọng nói, Thu lại thay bản nhận dạng chỉ khi lần nhận dạng mới thành công. Xóa câu hoặc bấm hủy bỏ được bản nháp; gửi lỗi giữ câu để sửa/gửi lại. Chỉ thêm tin người học sau khi gửi thành công; vẫn phân biệt lượt từ mic trên giao diện để không nhầm góp ý ngôn ngữ với chấm phát âm. Chống gửi kép, giữ Enter/IME, không để kết quả ghi âm cũ lọt sang buổi mới. Ô gõ vẫn hoạt động khi thiếu quyền mic hoặc Whisper lỗi.
- Dịch: công tắc trên trang mặc định **tắt** cho trình duyệt chưa có lựa chọn, nhớ lựa chọn riêng của trình duyệt. Khi bật, chỉ lời đáp AI (có thể lặp lại nội dung người học) được gửi tới Google Translate không chính thức. Biến `TRANSLATION_ENABLED=0` luôn thắng công tắc; giao diện cho biết dịch bị tắt trên máy chủ. Tắt dịch thì không gọi Google. Google/VOICEVOX lỗi không làm mất câu Nhật; giữ nút phát khi có audio và không coi trình duyệt chặn autoplay là lỗi bài.

## Hợp đồng kỹ thuật

- Thêm `POST /transcribe` nhận multipart `audio`, trả `{transcript}`. Dùng chung giới hạn multipart trước parser, validation định dạng/kích thước, timeout, khóa Whisper và dọn file của `/voice-chat`. Endpoint mới không đọc/ghi session hoặc gọi Ollama, VOICEVOX, Google. Giữ `/voice-chat` nhận dạng và gửi trong một request cho API client cũ. Giao diện mới dùng `/transcribe` rồi `POST /chat` với câu đã duyệt; bản ghi không lưu lâu dài.
- Mở rộng `POST /practice-sessions` nhận tùy chọn `lesson_id` cộng với các trường hiện có. Với bài nhanh, server dùng metadata mặc định theo `lesson_id`; với bài tùy chỉnh, giữ nguyên validation của `level`, `script`, `topic`. ID lạ trả 422 trước khi gọi Ollama. Kho lưu bài mẫu và chỉ dẫn theo bài ở backend là nguồn chuẩn; giao diện lấy danh sách và mặc định qua API đọc, không nhân bản metadata. Các response của bài nhanh thêm `progress` với ID bài, số lượt hoàn thành và tổng số lượt, kèm câu luyện lại khi hoàn thành; không thêm tiến độ cho luồng cũ. Tái sử dụng parser lời đáp/gợi ý hiện có.
- Thêm `translate` tùy chọn cho `/chat`, `/practice-sessions` và form `/voice-chat`; gửi giá trị rõ ràng từ UI, API client bỏ trường tiếp tục theo mặc định máy chủ. `/health` cho UI biết khả năng dịch được cấu hình, không dò Google. Bỏ qua adapter dịch hoàn toàn nếu tắt; giữ cache, timeout và fallback hiện có khi bật. Không lưu transcript, nội dung hội thoại hay cấu hình dịch của từng người ở server.
- Đo thời gian từ lúc dừng đến lúc có transcript, từ lúc xác nhận gửi đến lúc câu Nhật hiện, và đến lúc phát audio thực sự (`playing` nếu có). Giữ số đo cục bộ cho kiểm thử; không thêm telemetry hoặc thu thập nội dung câu. Không thay giao thức sang streaming trong MVP này.

## Nghiệm thu

- Pytest: `/transcribe` không đẩy history hoặc gọi upstream, có cùng bảo vệ upload và lỗi với `/voice-chat`; gửi câu đã sửa dùng đúng session. Bài nhanh có preset đúng, đếm lượt nói/gõ, không đếm lỗi, không vượt 5 lượt với request đồng thời, và vẫn tương thích bài tùy chỉnh/chat tự do. Kiểm chứng tắt dịch qua request và qua biến môi trường đều không gọi Google; hai lỗi TTS/dịch không làm mất text.
- Test JS: ghi → duyệt → gửi một lần; không ghi đè nháp gõ; giữ nháp khi lỗi; thu lại hoặc hủy không gửi; chức năng gõ, IME, fallback audio, dịch và điều khiển sau khi hoàn thành.
- Smoke trên trình duyệt thật: desktop + khung hẹp, một bài bằng mic thật nếu có người vận hành, một bài bằng bàn phím; thử từ chối mic, mất TTS và dịch tắt. Nếu chưa có người thử mic thật, tách kết quả thử bản ghi mẫu khỏi hạng mục mic vật lý trong `TEST_RESULTS.md`.
- Nghiệm thu với người học là bước riêng trước khi gọi MVP là đã kiểm chứng: 5 người lần đầu dùng, ít nhất 4 người tự hoàn thành một bài 5 lượt mà không cần hướng dẫn và chỉ ra được một câu muốn luyện lại. Ghi thời gian và vướng mắc, không ghi âm/câu riêng tư. Cung cấp kịch bản thử và mẫu ghi nhận trong repo; không giả lập người học để tuyên bố đạt mốc.
