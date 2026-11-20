# Thiết lập học tập cho trợ lý hội thoại

## Mục tiêu

Giúp người học luyện nói tiếng Nhật theo độ khó và tình huống mình chọn, đồng thời luyện nhận diện chữ mà không làm mất sự tự nhiên của cuộc hội thoại. Giữ luồng microphone → Whisper → Ollama → VOICEVOX chạy cục bộ và giữ ô nhập văn bản.

## Phương án đã chọn

1. Ép cả hội thoại sang một hệ chữ: dễ thấy lựa chọn có tác dụng, nhưng biến lời thoại thành dạng ít tự nhiên và làm lệch mục tiêu luyện nói.
2. Giữ lời thoại tiếng Nhật tự nhiên, dùng hệ chữ đã chọn cho bài luyện riêng: người dùng đã chọn cách này. Phần nghe và phần học tách nhau; VOICEVOX chỉ đọc lời thoại.

## Trải nghiệm đề xuất

- Trước khi luyện, người học có ba lựa chọn: **Trình độ** N5, N4, N3, N2, N1; **Luyện chữ** Hiragana, Katakana, Kanji; **Chủ đề** giao tiếp hằng ngày, tự giới thiệu, gia đình, trường học, công việc, sở thích, nhà hàng/quán cà phê, mua sắm, du lịch, thời tiết, JLPT, hoặc tự do. Mặc định: N5, Hiragana, giao tiếp hằng ngày. Nhớ lựa chọn trong trình duyệt.
- **Bắt đầu luyện** áp dụng cấu hình cho một buổi mới và cho trợ lý mở đầu bằng câu hỏi hoặc tình huống theo chủ đề. Trong cùng buổi, cả lượt nói và lượt gõ dùng một cấu hình và lịch sử. Khi chọn cấu hình khác, lời thoại đang có vẫn hiển thị cho đến khi người học chủ động bắt đầu buổi mới.
- Trợ lý ưu tiên câu hỏi nối tiếp bám vào điều người học vừa nói. N5 dùng câu và từ đơn giản hơn; các mức cao tăng dần độ phức tạp. Mức JLPT dùng để hướng dẫn độ khó, không phải cam kết mọi từ/câu thuộc đúng một danh mục JLPT.
- Mỗi lượt ưu tiên một phản hồi ngắn, có thể gồm hai câu để vừa đáp vừa hỏi tiếp. Bên dưới có mục **Gợi ý học tập** thu gọn mặc định: góp ý bằng tiếng Việt nếu có điểm đáng sửa, và một bài luyện Hiragana/Katakana/Kanji gắn với chủ đề hoặc lượt nói; đáp án chỉ hiện khi người học muốn xem. Không bịa lỗi khi câu đã đúng. Với lượt nói, nêu rõ góp ý dựa trên bản chép lời, không phải đánh giá phát âm.
- Ví dụ: **N5 · Katakana · Quán cà phê**. Trợ lý nói `コーヒーにしますか？` như bình thường. Phần luyện riêng hỏi `「コーヒー」は tiếng Việt nghĩa là gì?`, với đáp án ẩn `cà phê`.

## Phạm vi thực hiện

Thêm cấu hình học có giá trị hợp lệ kiểm tra ở backend và dùng chung cho lượt mở đầu, `/chat` và `/voice-chat`. Với buổi học, yêu cầu Ollama trả lời thoại và phần học dưới dạng các trường tách biệt; không đọc phần học qua TTS. Không dùng rule cố định cho buổi học vì rule bỏ qua chủ đề, trình độ và gợi ý; giữ hành vi hiện tại cho request cũ không tham gia buổi học. Lỗi ở phần gợi ý không được làm mất lời thoại hợp lệ; VOICEVOX offline vẫn hiển thị nội dung. Giữ HTML/CSS/JS thuần, không đổi provider hoặc model mặc định, không thêm database, chấm phát âm hay theo dõi tiến bộ dài hạn.

Kiểm chứng: chọn cả ba thiết lập, lưu qua tải lại trang, áp dụng đồng nhất cho giọng nói và văn bản, không đọc phần luyện qua VOICEVOX, không trộn ngữ cảnh khi bắt đầu buổi mới, và vẫn hoạt động nếu phần gợi ý hoặc tạo âm thanh gặp lỗi.
