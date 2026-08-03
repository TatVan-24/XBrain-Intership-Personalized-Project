# [DIRECTIVE #27] Bắt khi chất lượng AI trôi - phát hiện data/model drift

**Từ:** Ban Kỹ thuật AI & Nền tảng - TechX Corp
**Hiệu lực:** ngay khi nhận · **không yêu cầu deadline nộp** — mentor kiểm tra vào **cuối chương trình**
**Áp dụng:** nhóm AIO của mọi Task Force (bề mặt AIE: copilot + tóm tắt review)
**Mức độ:** ⭐ *nice-to-have / bonus* — **không bắt buộc**; làm được là điểm cộng, không làm không bị trừ như mandate lõi.

---

## Bối cảnh
Model AI chạy tốt lúc deploy, nhưng theo thời gian **phân phối đầu vào đổi** - khách hỏi kiểu mới, review đổi giọng, sản phẩm mới - làm chất lượng tóm tắt/trả lời **trôi khỏi baseline mà không ai hay**, vì nó vẫn "chạy" trơn tru. Không ai canh drift thì tới lúc phát hiện thì đã mất niềm tin. Nhiệm vụ: dựng cơ chế **tự phát hiện khi dữ liệu/model trôi** để can thiệp (retrain / điều chỉnh) **trước khi hỏng ngầm**.

## Yêu cầu
1. **Có baseline** - chốt phân phối đầu vào "bình thường" và/hoặc chỉ số chất lượng output baseline của model AI (trên bề mặt tóm tắt review / copilot).
2. **Phát hiện drift** - khi phân phối input dịch (traffic / review / query shift) **hoặc** chất lượng output trôi khỏi baseline quá ngưỡng → **flag drift**, chỉ ra bề mặt/metric nào đang trôi.
3. **Không báo giả** - dao động bình thường (theo giờ/ngày, mùa vụ) không được kích drift.
> Cách làm tự chọn; đã đạt thì chỉ cần chứng minh.

## Gợi ý hướng (không bắt buộc theo)
Chọn 1 hướng vừa sức, không cần đồ nặng:
- **Data drift (phân phối input):** PSI (Population Stability Index) · KS-test (numeric) / Chi-square (categorical) · KL–JS divergence.
- **Embedding drift (input là text — review/query):** embed input → khoảng cách tới centroid baseline / MMD / cosine drift (bắt "khách hỏi kiểu mới").
- **Output-quality drift (không cần nhãn):** theo cửa sổ trượt — abstention-rate ↑, fallback-rate ↑, citation-coverage ↓, judge-score ↓, độ dài/entropy output đổi.
- **Performance drift (nếu có nhãn/feedback):** faithfulness/accuracy giảm dần.
- *Thực dụng cho AI text:* baseline cửa sổ + **embedding-distance drift** trên query/review + track 1-2 proxy chất lượng (abstention / judge-score) → cảnh báo khi vượt ngưỡng.
- *Tool sẵn có:* Evidently AI · NannyML · Alibi-Detect · whylogs — hoặc tự viết PSI/KS vài chục dòng.

## Ràng buộc
- Giữ SLO/ngân sách; không đụng / vô hiệu hóa flagd; không hạ chuẩn.

## Cần kiểm chứng được (mentor kiểm vào cuối chương trình)
Không nộp gì. Hệ phải sẵn sàng để mentor tự đưa chuỗi kiểm vào:
- **Cửa replay nhận chuỗi dữ liệu từ ngoài** - mentor đưa một chuỗi có **shift phân phối** (hoặc đoạn suy giảm chất lượng) vào là chạy được.
- Hệ **xuất được tín hiệu drift** (metric/bề mặt nào trôi, tại thời điểm nào) để đối chiếu.

**Kiểm được (khi mentor đưa chuỗi):** chuỗi có shift → hệ **flag drift sau điểm shift** (chỉ đúng metric/bề mặt trôi); chuỗi ổn định → **không flag giả**.

## Được nhìn ở đâu
Trụ **AI** (AIE / MLOps giám sát chất lượng model). Chạm **Reliability** (chất lượng AI không rot ngầm).

> Điểm nằm ở chỗ bắt được lúc model **bắt đầu trôi** - trước khi khách nhận ra.

---

## English

# [DIRECTIVE #27] Catch it when AI quality drifts - detect data/model drift

**From:** AI Engineering & Platform Board - TechX Corp
**Effective:** immediately on receipt · **no submission deadline** — the mentor reviews it at the **end of the program**
**Applies to:** the AIO team of every Task Force (AIE surfaces: copilot + review summary)
**Level:** ⭐ *nice-to-have / bonus* — **not required**; doing it earns credit, skipping it is not penalized like a core mandate.

---

## Context
An AI model runs well at deploy time, but over time the **input distribution shifts** - customers ask in new ways, reviews change tone, new products appear - so the summary/answer quality **drifts away from baseline without anyone noticing**, because it still "runs" smoothly. With no one watching for drift, by the time you notice, trust is already lost. The task: build a mechanism to **detect when the data/model drifts** so you can intervene (retrain / adjust) **before it silently rots**.

## Requirements
1. **Have a baseline** - pin the "normal" input distribution and/or a baseline output-quality metric for the AI model (on the review-summary / copilot surface).
2. **Detect drift** - when the input distribution shifts (traffic / review / query shift) **or** output quality drifts past a threshold → **flag drift**, naming which surface/metric is drifting.
3. **No false alarms** - normal variation (time-of-day, seasonality) must not trip drift.
> Method is your choice; if you meet it, just prove it.

## Suggested approaches (not mandatory)
Pick one that fits the time; no heavy tooling needed:
- **Data drift (input distribution):** PSI (Population Stability Index) · KS-test (numeric) / Chi-square (categorical) · KL–JS divergence.
- **Embedding drift (text input — reviews/queries):** embed input → distance to baseline centroid / MMD / cosine drift (catches "customers asking in new ways").
- **Output-quality drift (label-free):** over a sliding window — abstention-rate ↑, fallback-rate ↑, citation-coverage ↓, judge-score ↓, output length/entropy shift.
- **Performance drift (if labels/feedback exist):** faithfulness/accuracy declining over time.
- *Pragmatic for text AI:* windowed baseline + **embedding-distance drift** on queries/reviews + track 1-2 quality proxies (abstention / judge-score) → alert on threshold breach.
- *Off-the-shelf tools:* Evidently AI · NannyML · Alibi-Detect · whylogs — or a few dozen lines of your own PSI/KS.

## Constraints
- Keep SLO/budget; do not touch / disable flagd; do not lower the bar.

## What must be verifiable (mentor checks at end of program)
Nothing to submit. The system must be ready for the mentor to feed a test series:
- **A replay entry accepting an external data series** - the mentor can drop in a series with a **distribution shift** (or a quality-degradation segment) and run it.
- The system can **emit a drift signal** (which metric/surface drifted, at what point) for comparison.

**Verifiable (when the mentor feeds a series):** a shifted series → the system **flags drift after the shift point** (naming the right metric/surface); a stable series → **no false flag**.

## Where it shows up
The **AI** pillar (AIE / MLOps model-quality monitoring). Touches **Reliability** (AI quality doesn't silently rot).

> The point is catching the moment the model **starts to drift** - before the customer notices.
