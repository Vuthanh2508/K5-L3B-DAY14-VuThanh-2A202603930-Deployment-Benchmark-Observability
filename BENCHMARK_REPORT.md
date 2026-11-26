# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Vũ Thành - 2A202603930
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows + Ubuntu 24.04 (WSL2), Python 3.12.3, Docker 29.7.2

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Với mock LLM cơ bản ~120–180ms (+20ms retrieval ở v2), 95% request thông thường hoàn thành ~220–290ms; ngưỡng 500ms giữ trải nghiệm chat phản hồi nhanh mà vẫn dung sai cho dao động tải vừa phải |
| Error rate `/ask` | `< 2.0 %` | Mock LLM có tỷ lệ lỗi upstream mặc định 1% (`MOCK_ERROR_RATE=0.01`), đặt SLO < 2% (error budget 2%) để phát hiện khi lỗi tăng bất thường vượt mức nền |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu `100%` sau chỉnh KB) | Đảm bảo chất lượng RAG của v2 không tụt dưới ngưỡng triển khai và chặn mọi bản thay đổi gây regression trong CI |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.5 | 190.5 | 220.6 | 1682.9 | 0.67% | PASS |
| 10 | 46.43 | 192.4 | 221.5 | 1662.6 | 1.00% | PASS |
| 50 | 104.1 | 200.5 | 291.0 | 1718.3 | 1.00% | PASS |
| 100 | 50.04 | 578.5 | 3741.5 | 4303.2 | 0.67% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính ở mức cao:
- Từ `concurrency=1` lên `10`, RPS tăng gần tuyến tính gấp ~10.3 lần (`4.5` → `46.43 req/s`) và p95 gần như không đổi (`220.6` → `221.5 ms`), vì agent chạy async I/O (`await asyncio.sleep`) chưa chạm giới hạn tài nguyên của 1 process uvicorn.
- Lên `concurrency=50`, RPS chỉ tăng thêm ~2.2 lần (`104.1 req/s`) và p95 nhích lên `291.0 ms`.
- Đến `concurrency=100`, hệ thống vượt điểm bão hòa của 1 process uvicorn/event loop: request xếp hàng chờ xử lý khiến p50 tăng lên `578.5 ms`, p95 vọt lên `3741.5 ms` (vi phạm SLO ≤ 500ms) và throughput **tụt ngược** xuống còn `50.04 req/s`.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 195.5 | 221.3 | 227.7 |
| 0.03 (mặc định) | 235.8 | 230.4 | 1688.7 |
| 0.1 | 397.6 | 1701.8 | 1719.7 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **p99** (và **p95** khi tỷ lệ chậm vượt 5%) nhạy nhất với request chậm:
  - Ở `MOCK_SLOW_RATE=0.03` (3% request chậm), `avg` chỉ tăng nhẹ từ `195.5` → `235.8 ms` và `p95` giữ ở `230.4 ms`, nhưng **`p99` nhảy vọt gấp ~7.4 lần lên `1688.7 ms`**.
  - Ở `MOCK_SLOW_RATE=0.1` (10% request chậm > 5%), `avg` mới là `397.6 ms` (vẫn dưới ngưỡng 500ms), trong khi **`p95` đã bùng lên `1701.8 ms`** (FAIL SLO).
- **Không nên đặt SLO theo average** vì số trung bình bị làm mượt bởi 90–97% request nhanh, che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.6 | 108.8 | 112.6 |
| Tổng cost (USD) | $0.000397 | $0.000758 | $0.000781 |
| Cost / câu đúng (USD) | $0.00039735 | $0.00003607 | $0.00003397 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "xác thực"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT là token có chữ ký số và thời gian hết hạn |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa"], ...)` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale pod dựa trên CPU, memory và custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 bổ sung bước retrieval (`KNOWLEDGE_BASE`) giúp accuracy tăng từ **4.3%** (1/23) lên **91.3%** (21/23), và **100%** (23/23, 0 regression) sau khi bổ sung 2 mục còn thiếu.
- **Chi phí:** v2 tốn gấp ~1.92 lần token/câu (`108.8` so với `56.6` ở v1) vì prompt có thêm context, nên tổng cost cao gần gấp đôi (`$0.000758` vs `$0.000397`). Tuy nhiên **cost / câu đúng** của v2 lại **rẻ hơn ~11 lần** (`$0.00003607` — và `$0.00003397` sau khi sửa KB — so với `$0.00039735` ở v1) vì v1 gần như trả lời sai hết.
- **Latency:** v2 chậm hơn một chút ở p50/p95 (`p50=184.6ms`, `p95=214.3ms` so với `p50=157.6ms`, `p95=183.5ms` của v1) do thêm bước retrieval ~20ms + prompt dài hơn. Lưu ý ở lần chạy `eval_v2_fixed.json`, `p95=1521.3ms` do có 2/23 câu dính `MOCK_SLOW_RATE=0.03` — minh họa rằng mẫu 23 câu eval quá nhỏ để đánh giá latency, phải đo latency bằng `load_test.py`.
- **Quality gate trong CI:** `eval/run_eval.py` trả **exit code `1`** nếu `accuracy < --min-accuracy` hoặc có bất kỳ câu nào bị regression so với `--baseline` (khi test v1 với `--baseline reports/eval_v2.json`, có 20 câu regression nên Quality gate `FAIL` và trả `exit code 1`). Trong GitHub Actions (`.github/workflows/eval.yml` chạy trên `pull_request`), chỉ cần bật agent và chạy `python eval/run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2.json` — exit code `1` sẽ tự động làm step/job fail và chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
