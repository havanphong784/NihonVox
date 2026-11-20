# Bản dịch dưới lời đáp AI

Thiết kế đã được người dùng duyệt trong hội thoại: dùng Google Translate không cần API key để dịch Nhật → Việt. Chỉ văn bản `reply` cuối cùng của AI được gửi tới Google; không gửi input người học, microphone, transcript, lịch sử, phần góp ý hoặc bài tập. Lời thoại vẫn do Ollama/VOICEVOX xử lý local; dịch là ngoại lệ có kết nối ngoài máy.

Bản dịch hiển thị ngay dưới câu tiếng Nhật ở mọi lời đáp (mở buổi học, lượt gõ, lượt nói, rule). Render bằng `textContent`, `lang=vi`; VOICEVOX chỉ đọc nguyên văn tiếng Nhật. Gắn nhãn “Bản dịch Google · Tiếng Việt”. Nếu dịch lỗi, giữ câu Nhật/audio và hiển thị thông báo ngắn, không làm cả lượt hội thoại thất bại.

Dùng backend httpx hiện có gọi endpoint không chính thức `https://translate.googleapis.com/translate_a/single` với `client=gtx`, `sl=ja`, `tl=vi`, `dt=t`. Endpoint đã thử với câu mẫu không chứa dữ liệu riêng và trả HTTP 200. Không dùng thư viện giả lập trình duyệt hay tạo API key. Google có thể thay đổi/chặn endpoint; không cam kết miễn phí vĩnh viễn, SLA hoặc chính xác tuyệt đối.

Cache thành công trong RAM tối đa 256 câu/1 giờ, không cache lỗi; timeout toàn bộ dịch tối đa 6 giây, chạy song song với tạo WAV. Có biến `TRANSLATION_ENABLED=0` để trở lại chế độ không gửi lời đáp ra ngoài; mặc định bật theo yêu cầu đã duyệt. Không thêm dependency, database, dịch input, hoặc đổi provider/model. Không tự commit thay đổi mới.

Kiểm chứng: parse nhiều đoạn Google; cache/expiry/capacity; timeout/429/response rỗng hoặc hỏng vẫn giữ chat/audio; đúng nội dung gửi (chỉ reply); không dịch qua health; các loại lượt đều có bản dịch; TTS vẫn tiếng Nhật; XSS và UI mobile; endpoint Google thật với câu mẫu, API app thật và trình duyệt.
