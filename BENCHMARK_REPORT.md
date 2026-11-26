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

- **Chất lượng:** v2 bổ sung bước retrieval (`KNOWLEDGE_BASE`) giúp accuracy tăng từ **4.3%** (1/23) lên **91.3%** (21/23), và **100%** (23/23, 0 regression) sau khi bổ sung 2 mục còn thiếu
- **Chi phí:** v2 tốn gấp ~1.92 lần token/câu (`108.8` so với `56.6` ở v1) vì prompt có thêm context, nên tổng cost cao gần gấp đôi (`$0.000758` vs `$0.000397`). Tuy nhiên **cost / câu đúng** của v2 lại **rẻ hơn ~11 lần** (`$0.00003607` — và `$0.00003397` sau khi sửa KB — so với `$0.00039735` ở v1) vì v1 gần như trả lời sai hết
- **Latency:** v2 chậm hơn một chút ở p50/p95 (`p50=184.6ms`, `p95=214.3ms` so với `p50=157.6ms`, `p95=183.5ms` của v1) do thêm bước retrieval ~20ms + prompt dài hơn. Lưu ý ở lần chạy `eval_v2_fixed.json`, `p95=1521.3ms` do có 2/23 câu dính `MOCK_SLOW_RATE=0.03` — minh họa rằng mẫu 23 câu eval quá nhỏ để đánh giá latency, phải đo latency bằng `load_test.py`
---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png` — thấy rõ Golden Signals: Traffic, Error rate, p95, In-flight, Instances up = 3, LLM cost 1h)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png` — `chat mock-llm-small` chiếm ~1690.6 ms / 1709.8 ms)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png` — `trace_id=19f0f7eb9e6ad9bb312a4f281945e433`, có event `exception: Upstream LLM error: 503 Service Unavailable`)
- [x] Trang Alerts của Prometheus với **4/4 alert đang firing** (`screenshots/prometheus-alert-firing.png` — `LLMCostBurnRateHigh`, `AgentHighErrorRate`, `AgentHighLatencyP95`, `AgentInstanceDown`)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | ~1.5 phút (`16:40` đổi → Pending → `16:42` Firing) | **Error rate** (đỏ `18.42%`), **Requests/s theo status code** (`503`), **LLM calls theo kết quả** (`error`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | ~2 phút (`16:40` đổi → Pending → `16:42` Firing) | **Latency p95** (đỏ `1.92 s`), **Latency `/ask` — p50/p95/p99**, **LLM latency p95 theo model** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | Đã firing sẵn do `rate([5m])` tích lũy từ tải cao trước đó (~2 phút sau ngưỡng > $2/h); khi bật `mock-llm-large` vọt lên ~$18/h | **Cost burn rate (USD/giờ)** (vọt lên ~$18/h), **LLM cost (1h)** (đỏ `$2.1766`) |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`) | ~30–45 giây (`16:43` pause → Pending → Firing) | **Instances up** (3 → 2), **Requests/s theo instance** (mất lưu lượng instance bị pause) |
| E | `AGENT_VERSION=v1` | Không có alert nào | Không firing (`agent-slo` về Inactive; cost chờ hết cửa sổ 5m hạ xuống) | **Retrieval hit ratio** (mất), **Tokens/s** (giảm), bảng **Phiên bản đang chạy** (`v1`) |

*(Ghi chú quan sát Exercise 7.4 & 7.6:*
- *Khoảng cách `avg` ↔ `p95`/`p99` trên Grafana phản ánh tail latency (phần lớn request ~190ms nhưng 3% request ~1.7s kéo `p99` lên cao).*
- *`Input tokens/s` luôn cao hơn `Output tokens/s` (vd trong trace mẫu: `83` input vs `44` output tokens) vì agent v2 ghép thêm `SYSTEM_PROMPT` và context retrieval từ `KNOWLEDGE_BASE` vào prompt.*
- *`curl -i http://localhost:8080/metrics` trả `HTTP 404 Not Found` vì `nginx.conf` chặn `/metrics` từ bên ngoài (`location = /metrics { return 404; }`), tránh lộ thông tin nội bộ; chỉ Prometheus trong mạng Docker scrape trực tiếp `agent:8000/metrics`.*
- *Dùng `docker pause` thay vì `docker stop` ở thí nghiệm D vì `stop` làm container biến mất khỏi Docker DNS (Prometheus coi target không tồn tại nên không alert), còn `pause` giữ DNS nhưng không phản hồi → `up == 0`. Lỗi 504 nếu xảy ra ở Nginx khi chờ quá timeout cũng không hiện trên dashboard của agent vì request chưa kịp được agent ghi metric.)*

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Observability hạ tầng (Prometheus/Grafana) chỉ đo tình trạng kỹ thuật (latency, HTTP 5xx, CPU, uptime), hoàn toàn không biết câu trả lời đúng hay sai về mặt nội dung. Để phát hiện sự cố suy giảm chất lượng như nhầm sang `v1`:
1. **Chặn ngay từ CI/CD (Quality Gate):** Chạy `eval/run_eval.py` trên golden dataset kèm `--baseline` và `--min-accuracy` trước khi merge/deploy (như CP7 đã thấy v1 bị 20 regression và fail với exit code `1`).
2. **Giám sát chất lượng trên production (Online Eval & Business Metrics):** Đặt alert khi **Retrieval hit ratio** tụt bất thường (vd giảm về 0%), theo dõi tỷ lệ phản hồi tiêu cực từ người dùng (thumbs down / retry), và lấy mẫu định kỳ câu trả lời thực tế chấm bằng **LLM-as-a-judge**.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `01e4fca4441ae5f6f2af5629b8b2e8a0`
- Tổng thời gian: `1709.8 ms` (~`1.7 s` trên Jaeger)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1690.6 ms`, chiếm **`98.9%`** tổng thời gian; bước `agent.retrieve_context` chỉ mất `15.4 ms`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:36:48.327998+00:00", "level": "INFO", "service": "observable-agent", "instance": "975888ebb4f4", "event": "llm_call", "trace_id": "01e4fca4441ae5f6f2af5629b8b2e8a0", "span_id": "3f30fdfdbef1db0f", "request_id": "9565462efa31", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1690.6}
{"ts": "2026-11-26T09:36:48.328715+00:00", "level": "INFO", "service": "observable-agent", "instance": "975888ebb4f4", "event": "http_request", "trace_id": "01e4fca4441ae5f6f2af5629b8b2e8a0", "span_id": "3f30fdfdbef1db0f", "request_id": "9565462efa31", "method": "POST", "route": "/ask", "status": 200, "ms": 1709.8}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.23 | 200 | 350 | 1700 | 64 (0.83%) |
| 3 | 65.78 | 190 | 230 | 1700 | 89 (1.14%) |

*(Ghi chú số liệu `Aggregated` khớp với `scale_1_stats.csv` và `scale_3_stats.csv`; riêng `POST /ask`: 1 instance `59.28 req/s`, `p95=390 ms`, `p99=1700 ms` vs 3 instances `59.80 req/s`, `p95=230 ms`, `p99=1700 ms`.)*

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **RPS gần như giữ nguyên** (`65.23` → `65.78 req/s`) vì `locustfile.py` có `wait_time = between(0.5, 2)`s nên tải tự nhiên của 100 users chỉ quanh ~65 req/s.
- **`p95` có giảm từ `350 ms` xuống `230 ms`** (riêng `/ask` giảm từ `390 ms` xuống `230 ms`, `/health` giảm từ `56 ms` xuống `9 ms`) do ở 1 instance (`0.5 CPU`) bắt đầu xuất hiện độ trễ xếp hàng nhẹ; khi chia tải sang 3 instance qua Nginx round-robin, độ trễ hàng đợi gần như biến mất.
- **Tuy nhiên `p50` (`200 ms`) và `p99` (`1700 ms`) hầu như không đổi** — vì **nút thắt thời gian chính nằm ở thời gian gọi LLM (`llm_request_duration_seconds`: ~120–180ms + 3% request chậm ~1.7s)**. Dù tăng số lượng container agent, mỗi request vẫn phải chờ từng đó thời gian phản hồi từ LLM upstream (và tỷ lệ lỗi ~1% từ LLM vẫn giữ nguyên).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Không đánh giá latency bằng average và không đo latency bằng tập eval nhỏ:** `avg` che giấu tail latency của nhóm người dùng gặp chậm (`p95`/`p99`), còn tập eval 23 câu quá nhỏ nên dễ nhiễu chỉ số tốc độ — phải đo tốc độ bằng load test nhiều request và đặt SLO theo percentile.
  2. **Kết hợp 3 trụ cột Metrics – Traces – Logs để debug nhanh:** Dashboard Grafana báo *có sự cố gì* (`p95` tăng), Jaeger chỉ rõ *chậm ở span nào* (`chat mock-llm-small` chiếm ~98.9% thời gian, không phải retrieval), và `trace_id` nối thẳng sang log JSON để xem chi tiết token, cost, lỗi của đúng request đó.
  3. **Hạ tầng xanh không đồng nghĩa chất lượng tốt:** Đổi sang `v1` không làm alert hạ tầng nào firing dù accuracy rớt từ 100% xuống 4.3%, nên production bắt buộc phải có **eval quality gate trong CI** (chọn thước đo như `cost / câu đúng`) và giám sát các chỉ số chất lượng như retrieval hit ratio.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Kết nối Alertmanager gửi thông báo qua **Slack / PagerDuty**; thêm metric & alert ở tầng **Load Balancer / Nginx** (bắt lỗi `504` / `502` mà backend không tự ghi nhận được); thêm alert khi **`Retrieval hit ratio` giảm mạnh** dưới ngưỡng; theo dõi **Redis latency / memory usage** và **Rate limit (`429`) / Budget exceeded (`402`) rate** để phát hiện sớm spam hoặc sắp chạm ngưỡng chi phí.
