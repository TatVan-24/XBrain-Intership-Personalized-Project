# [DIRECTIVE #28] Sự cố kéo dài không được biến thành "bình thường"

**Từ:** Ban Vận hành (SRE) - TechX Corp
**Hiệu lực:** ngay khi nhận · **không yêu cầu deadline nộp** — mentor kiểm tra vào **cuối chương trình**
**Áp dụng:** nhóm AIO của mọi Task Force

---

## Bối cảnh
Sự cố thật hiếm khi kết thúc trong một hai phút - có cái kéo dài cả tiếng. Một hệ phát hiện non tay, sau một lúc, sẽ **coi tình trạng lỗi kéo dài đó là mức bình thường mới** và thôi cảnh báo - đúng lúc khách vẫn đang chịu trận. Tệ hơn: trong lúc sự cố đầu chưa dứt, một sự cố khác nổ chồng lên mà hệ đã "quen" nên bỏ lọt. Hệ AIOps của các bạn phải đứng vững suốt một sự cố dài mà không tự mù, cũng không la làng vì tải thay đổi hợp lệ.

## Yêu cầu
1. **Phát hiện liên tục suốt sự cố dài** - một sự cố kéo dài nhiều chục phút phải được báo **xuyên suốt** tới khi thật sự hết, không có "khoảng câm" giữa chừng.
2. **Không báo nhiễu vì tải hợp lệ đổi** - trong lúc sự cố diễn ra, lưu lượng bình thường vẫn dao động theo giờ; hệ không được đẻ báo giả chỉ vì mức "bình thường" đã dịch.
3. **Vẫn bắt được sự cố mới nổ chồng** - nếu một sự cố thứ hai xuất hiện ở service khác giữa lúc sự cố đầu chưa dứt, hệ phải phát hiện và **tách riêng**, không để cái đầu che cái sau.
> Cách làm tự chọn; đã đạt thì chỉ cần chứng minh.

**Gợi ý:** median/MAD trượt nhưng **freeze baseline khi đang alert** (chống tự-nuốt anomaly) · burn-rate đa cửa sổ · per-service isolation để tách sự cố chồng.

## Ràng buộc
- Giữ SLO/ngân sách; không đụng / vô hiệu hóa flagd; không hạ chuẩn để qua bài.

## Cần kiểm chứng được (mentor kiểm vào cuối chương trình)
Không nộp gì. Hệ phải sẵn sàng để mentor tự đưa kịch bản kiểm vào:
- **Cửa replay nhận kịch bản từ ngoài** — mentor đưa một sự cố kéo dài (tải nền vẫn dao động, có thể chồng thêm sự cố thứ 2) vào là chạy được.
- Xuất được **dòng cảnh báo theo thời gian + danh sách incident** để đối chiếu.

**Kiểm được (khi mentor đưa kịch bản):** báo **liên tục** suốt sự cố dài (không có khoảng câm); **không báo giả** vì tải hợp lệ đổi; sự cố thứ 2 nổ chồng → **phát hiện + tách riêng**.

## Được nhìn ở đâu
Trụ **AI** (AIOps). Chạm **Reliability** + **Operational Excellence**.

> Điểm nằm ở chỗ hệ **không quen với cái sai** - sự cố kéo dài bao lâu vẫn là sự cố, và mắt vẫn mở để thấy cái tiếp theo.

---

## English

# [DIRECTIVE #28] A long incident must never become "the new normal"

**From:** Operations (SRE) - TechX Corp
**Effective:** immediately on receipt · **no submission deadline** — the mentor reviews it at the **end of the program**
**Applies to:** the AIO team of every Task Force

---

## Context
Real incidents rarely end in a minute or two - some last an hour. A naive detector, after a while, will **treat the sustained fault as the new normal** and stop alerting - exactly while customers are still suffering. Worse: while the first incident is still open, a second one erupts elsewhere and the system, now "used to it", misses it. Your AIOps system must hold up through a long incident without going blind, and without crying wolf because legitimate load shifted.

## Requirements
1. **Continuous detection through a long incident** - a fault lasting tens of minutes must stay alerted **throughout** until it truly clears, with no "silent gap" in the middle.
2. **No false alarms from legitimate load change** - during the incident, normal traffic still varies by time of day; the system must not fire just because the "normal" level moved.
3. **Still catch a new incident stacked on top** - if a second incident appears on another service while the first is unresolved, the system must detect and **separate** it, not let the first mask the second.
> Method is your choice; if you meet the bar, just prove it.

**Hints:** rolling median/MAD but **freeze the baseline while alerting** (avoid self-absorbing the anomaly) · multi-window burn-rate · per-service isolation to separate a stacked incident.

## Constraints
- Hold SLO/budget; do not touch or disable flagd; do not lower the bar to pass.

## What must be verifiable (mentor checks at end of program)
Nothing to submit. The system must be ready for the mentor to feed a test scenario:
- **A replay entry accepting an external scenario** — the mentor can drop in a long-running incident (background traffic still varying, optionally a second incident stacked on top) and run it.
- It can emit **the alert stream over time + the list of incidents** for comparison.

**Verifiable (when the mentor feeds a scenario):** alerts fire **continuously** through the long incident (no silent gap); it does **not** false-alarm on legitimate traffic shifts; a second stacked incident is **detected and kept separate**.

## Where it shows up
The **AI** pillar (AIOps). Touches **Reliability** + **Operational Excellence**.

> The score is in the system **not getting used to what's wrong** - however long an incident lasts it is still an incident, and the eyes stay open for the next one.
