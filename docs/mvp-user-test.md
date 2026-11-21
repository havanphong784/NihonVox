# NihonVox — Kịch bản kiểm thử người học

## Mục đích

Xác minh người học tiếng Nhật lần đầu có thể tự hoàn thành một bài luyện nhanh 5 lượt và nhận ra một câu muốn luyện lại. Đây là kiểm thử trải nghiệm, không phải bài thi tiếng Nhật.

## Chuẩn bị

- Dùng bản NihonVox chạy local trên `http://127.0.0.1:8000`.
- Mở cửa sổ riêng hoặc xóa localStorage trước mỗi người thử; không yêu cầu đăng nhập.
- Nếu thử bằng microphone, xin quyền mic sau khi bấm **Nói**. Nếu không có mic, dùng bàn phím và ghi rõ trong kết quả.
- Không yêu cầu người thử đọc câu riêng tư, tên thật hoặc dữ liệu cá nhân. Không ghi âm và không lưu nội dung câu ngoài ghi chú tổng hợp.

## Kịch bản cho người điều phối

1. Nói: “Hãy tự dùng trang này để hoàn thành bài luyện nhanh. Bạn có thể gõ hoặc nói tiếng Nhật. Mình sẽ không hướng dẫn thao tác trừ khi bạn bị kẹt.”
2. Chọn một bài khác nhau theo bảng phân bổ bên dưới, rồi bấm **Bắt đầu bài nhanh**.
3. Để người thử tự hoàn thành 5 lượt. Nếu dùng microphone, yêu cầu họ kiểm tra và sửa transcript trước khi bấm **Gửi**.
4. Khi trang báo hoàn thành, hỏi: “Câu nào bạn muốn luyện lại?” Không yêu cầu họ đọc lại câu đó.
5. Ghi thời gian từ lúc bắt đầu đến khi hoàn thành, liệu họ có cần trợ giúp, điểm gây bối rối, và nhận xét về câu muốn luyện lại.
6. Kết thúc bằng câu: “Bạn có muốn dùng lại app này cho một bài tương tự không?” Không thuyết phục hay giải thích thay cho người thử.

## Tiêu chí

- **Hoàn thành không hướng dẫn:** người thử tự mở bài và hoàn tất 5 lượt.
- **Thời gian:** tính bằng phút, làm tròn 0,1 phút.
- **Vướng mắc:** mô tả hành vi quan sát được, không suy đoán nguyên nhân.
- **Câu muốn luyện lại:** chỉ ghi bản dịch/mô tả tổng quát nếu người thử tự nói ra; không ghi câu riêng tư.
- **Đạt MVP trải nghiệm:** ít nhất 4/5 người hoàn thành một bài 5 lượt không cần hướng dẫn và chỉ ra được một câu muốn luyện lại.

## Phân bổ và mẫu ghi nhận

| Người thử | Bài | Hoàn thành không hướng dẫn | Thời gian (phút) | Vướng mắc quan sát được | Câu muốn luyện lại (không riêng tư) |
|---|---|---:|---:|---|---|
| P1 | Gọi món | — | — | — | — |
| P2 | Tự giới thiệu | — | — | — | — |
| P3 | Hỏi đường | — | — | — | — |
| P4 | Gọi món | — | — | — | — |
| P5 | Tự giới thiệu | — | — | — | — |

**Kết quả:** Chưa thực hiện trong môi trường tự động. Không điền bảng bằng dữ liệu giả; sau khi có người tham gia, cập nhật số đạt và các vướng mắc thực tế vào `TEST_RESULTS.md`.
