# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / eval set SHA:** `E-swarm-20261117-d52a` / `d52a6cd176d8`
- **Phiên bản:** code (commit) … · eval set v1 (sha …) · metric_spec … · grader (commit) … · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed, nguồn lab8_public; nhãn: labels_v1.json
- **Metric & ngưỡng:** (trích metric_spec.yaml)
- **Kết quả baseline vs PR:** baseline pass_rate=0.9857; fixed=1.0000 (Δ +0.014, CI [0.000, +0.043]); seeded_regression=0.7143 (Δ −0.271, CI [−0.500, −0.057], blocked).
- **Judge:** tone κ=0.757, P=0.857, R=0.800 đạt floor; helpful κ=0.375, P=1.000, R=0.300 nên loại.
- **Trace case:** link `docs/trace_case.md`, bước sai đầu tiên, regression test
- **Gate owner:** eval owner điều tra trace; waiver cần tech lead duyệt.
- **Phạm vi pilot:** đánh giá offline agent xử lý claim hoàn tiền LogiX-VN.
- **Giới hạn / bằng chứng còn thiếu:** MockLLM, 14 item, judge replay; không đo trên người dùng thật
- **Khi nào tăng eval-set version:** thêm adversarial pack, trace regression, hoặc đổi nhãn/phạm vi item.

## v2: slice, nhiễu và integrity

- A/A MockLLM với seed 66/77/88/99/110 có Δ=0; sàn `pass_hat_5`=0.80 thấp hơn baseline 0.8929.
- FM-08 baseline agreement là 0.4857 (v1) và 0.55 (v2); sàn tương ứng đặt ở 0.45/0.50, kèm paired no-drop check để baseline swarm không tự fail.
- Slice `money_movement` bắt sai khoản tiền; `adversarial` theo dõi prompt injection và principal boundaries.
- 5 seed không phát hiện ổn định lỗi 1/3 seed; tăng seed hoặc thêm regression item.
