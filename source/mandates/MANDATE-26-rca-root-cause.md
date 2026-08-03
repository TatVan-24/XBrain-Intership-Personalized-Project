# [DIRECTIVE #26] RCA phải chỉ đúng gốc - không dừng ở triệu chứng, không nhầm tương quan

**Từ:** Ban Vận hành (SRE) & AI - TechX Corp
**Hiệu lực:** ngay khi nhận · **không yêu cầu deadline nộp** — mentor kiểm tra vào **cuối chương trình**
**Áp dụng:** nhóm AIO của mọi Task Force

---

## Bối cảnh
Phát hiện được sự cố mới là bước đầu; nói **đúng vì sao** mới là thứ cứu được thời gian lúc dầu sôi lửa bỏng. Sự cố thật hiếm khi gọn: nó lan chuyền qua nhiều service, và nhiều thứ biến động cùng lúc chỉ vì trùng hợp. Một RCA chỉ đúng khi nó **chỉ tới gốc thật**, chịu được cả cái chưa từng thấy.

## Yêu cầu
**Sàn (cần đạt):**
1. **Chỉ ra service nghi phạm gốc + giải thích bằng bằng chứng** - khi sự cố lan chéo nhiều service, RCA tự đưa ra **một** service nghi là gốc, kèm lý lẽ dựa trên bằng chứng (trace / topology / tín hiệu), **không chỉ liệt kê service đang đỏ** và không dừng ở triệu chứng downstream.

**Nice-to-have (điểm cao, không bắt buộc):**
2. **Không nhầm tương quan thành nhân quả** - loại được nghi phạm chỉ tình cờ biến động cùng lúc.
3. **Chịu được sự cố kiểu chưa từng thấy** - chỉ đúng gốc cả với kịch bản ngoài bộ đã biết, không phải học tủ fault mẫu.
> Cách làm tự chọn; đã đạt thì chỉ cần chứng minh. Độ chính xác tuyệt đối dưới nhiễu/ca lạ là phần cộng - sàn là **attribution có lý lẽ**, không phải RCA hoàn hảo.

**Gợi ý:** dependency-graph + downstream-weighting · trace span-error propagation · thứ tự thời gian (cái đỏ trước = gốc, loại tương quan) · multi-signal scoring.

## Ràng buộc
- Giữ SLO/ngân sách; không đụng / vô hiệu hóa flagd; không hạ chuẩn để qua bài.

## Cần kiểm chứng được (mentor kiểm vào cuối chương trình)
Không nộp gì. Hệ phải sẵn sàng để mentor tự đưa ca kiểm vào và verify tại chỗ:
- **Cửa replay nhận kịch bản/trace từ ngoài** — mentor đưa một sự cố lan chéo nhiều service vào là chạy được ngay.
- **RCA xuất ranking nghi phạm + giải thích** vì sao chọn service đó làm gốc.

**Kiểm được (khi mentor đưa ca):** *Sàn* — RCA đưa ra **một service nghi phạm gốc kèm lý lẽ dựa trên bằng chứng**, không chỉ liệt kê service đỏ, không dừng ở triệu chứng downstream. *Điểm cao* — **không bị tín hiệu tương quan nhiễu đánh lạc** và chỉ đúng gốc cả với ca ngoài bộ đã biết.

## Được nhìn ở đâu
Trụ **AI** (AIOps): chẩn đoán đúng nguyên nhân. Chạm **Reliability** + **Operational Excellence** (giảm MTTR).

> **chỉ đúng gốc dưới nhiễu và với cái lạ** - thứ chỉ đội thật sự hiểu hệ mới làm được.

---

## English

# [DIRECTIVE #26] RCA must point at the true root — not stop at symptoms, not mistake correlation

**From:** Operations (SRE) & AI — TechX Corp
**Effective:** immediately on receipt · **no submission deadline** — the mentor reviews it at the **end of the program**
**Applies to:** the AIO team of every Task Force

### Context
Detecting an incident is step one; saying **why** correctly is what saves time when things are on fire. Real incidents are rarely clean: they cascade across services, and many things move at once purely by coincidence. An RCA is only right when it **points at the true root** and holds up against the unseen.

### Requirements
**Floor (required):**
1. **Name a suspected root service + justify it with evidence** — when a fault chains across services, RCA proposes **one** suspected root, with reasoning grounded in evidence (trace / topology / signals); it does **not** just list the services currently red, nor stop at a downstream symptom.

**Nice-to-have (higher score, not required):**
2. **Don't mistake correlation for causation** — rule out suspects that merely moved at the same time.
3. **Hold up against unseen incident types** — correct on scenarios outside the known set, not because you memorized sample faults.
> The method is your choice; if you meet it, just prove it. Perfect accuracy under noise/novel cases is bonus — the floor is **justified attribution**, not flawless RCA.

**Hints:** dependency graph + downstream weighting · trace span-error propagation · temporal order (what went red first = root, rules out correlation) · multi-signal scoring.

### Constraints
- Keep SLO/budget; do not touch / disable flagd; no lowering the bar to pass.

### What must be verifiable (mentor checks at end of program)
Nothing to submit. The system must be ready for the mentor to feed a test case and verify on the spot:
- **A replay entry accepting external scenarios/traces** — the mentor can drop in a cross-service cascade and run it immediately.
- **RCA emits a suspect ranking + an explanation** of why it chose that root service.

**Verifiable (when the mentor feeds a case):** *Floor* — RCA proposes **one suspected root service with evidence-based reasoning**, not just a list of red services, not stopping at a downstream symptom. *Higher score* — **not thrown off by a correlated noise signal** and correct on scenarios outside the known set.

### Where it shows up
The **AI** pillar (AIOps): correct root-cause diagnosis. Touches **Reliability** + **Operational Excellence** (lower MTTR).

> **the right root under noise and with the unseen** — only a team that truly understands the system can do it.
