# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | đạt | dùng cho tone |
| helpful | 100 | 0.375 | 1.000 | 0.300 | không đạt | loại khỏi gate |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người | Câu tuyên bố hoàn tiền; yêu cầu judge kiểm trạng thái rõ ràng. |
| 2 | H-017 | PASS | FAIL | Người | Khẳng định hoàn thiếu căn cứ; bổ sung negative anchor. |
| 3 | H-029 | PASS | FAIL | Người | Bảo khách chờ nhưng không giải quyết yêu cầu. |
| 4 | H-042 | FAIL | PASS | Judge | Reply hoàn tiền rõ ràng, lịch sự; thêm positive anchor. |
| 5 | H-051 | FAIL | PASS | Judge | “refund” tương đương hoàn tiền; đưa biến thể Việt/Anh vào rubric. |

## Kết luận
- helpful bị loại: FN=21, recall 0.30, κ=0.375 dù precision=1.00; judge bỏ sót nhiều reply không hữu ích.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
