# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **Hardcode secret trong source code (`develop/app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Đã sửa trong `production/config.py` (dòng 27, 32): đọc qua `os.getenv("OPENAI_API_KEY", "")` và `os.getenv("AGENT_API_KEY", "")`, tách cấu hình mẫu ra `.env.example` (`.env` nằm trong `.gitignore`).

2. **Hardcode cấu hình, không đọc từ biến môi trường (`develop/app.py` dòng 21–22):**
   - `DEBUG = True` và `MAX_TOKENS = 500` gắn cứng trong code, muốn đổi giữa `development`/`staging`/`production` phải sửa source.
   - Đã sửa trong `production/config.py` (dòng 15–35, 37–46): gom vào `@dataclass Settings` đọc từ `os.getenv(...)` và `validate()` để fail-fast khi thiếu cấu hình bắt buộc ở `production`.

3. **Dùng `print()` thay cho structured logging và làm lộ secret ra log (`develop/app.py` dòng 33–38):**
   - Dòng 34 in thẳng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` ra stdout.
   - Đã sửa trong `production/app.py` (dòng 28–32, 111–122): dùng `logging` định dạng JSON (`{"time":...,"level":...,"msg":...}`) và chỉ log `question_length`, `client_ip`, `response_length`, không log secret.

4. **Không có health check / readiness check (`develop/app.py` dòng 42–43):**
   - Chỉ có `GET /`, không có `/health` (liveness) hay `/ready` (readiness) để platform/load balancer kiểm tra tình trạng sống và sẵn sàng nhận traffic.
   - Đã sửa trong `production/app.py` (dòng 135–161): bổ sung `GET /health` và `GET /ready` (trả `503` khi `is_ready == False`).

5. **Bind cứng `host="localhost"`, `port=8000` và bật `reload=True` (`develop/app.py` dòng 49–53):**
   - `host="localhost"` khiến container không nhận được kết nối từ bên ngoài; `port=8000` không dùng `PORT` do Railway/Render cấp; `reload=True` gây tốn tài nguyên và không an toàn trên production.
   - Đã sửa trong `production/app.py` (dòng 194–198) và `production/config.py` (dòng 17–19): mặc định `HOST="0.0.0.0"`, `PORT` từ env var, `reload=settings.debug` (mặc định `False`).

6. **Không có lifecycle & graceful shutdown khi nhận `SIGTERM` (`develop/app.py`):**
   - Server bị tắt đột ngột có thể cắt ngang request đang xử lý.
   - Đã sửa trong `production/app.py` (dòng 39–67, 180–189): dùng `@asynccontextmanager async def lifespan(app)` để quản lý `startup`/`shutdown` (`is_ready = False` trước khi tắt) và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)`.

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh gọi (`POST /ask` nhận `question` qua query string):

```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Output trả về ở client:

```json
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Log phía server (`01-localhost-vs-production/develop/app.py`) cho thấy anti-pattern in key ra stdout:

```text
Starting agent on localhost:8000...
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.
INFO:     127.0.0.1:38800 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

Kết quả kiểm tra bản `production` (`01-localhost-vs-production/production/app.py`):

```text
INFO:     127.0.0.1:41590 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:60594 - "GET /ready HTTP/1.1" 200 OK    # {"ready":true}
INFO:     127.0.0.1:60604 - "POST /ask HTTP/1.1" 200 OK
```

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop | Production | Tại sao quan trọng? |
| --- | --- | --- | --- |
| Config & Secrets | Hardcode trực tiếp (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS`) | Đọc từ biến môi trường qua `Settings` (`config.py`) + `.env.example`, fail-fast khi thiếu secret ở `production` | Tránh lộ mật khẩu/API key khi push lên GitHub; thay đổi được cấu hình giữa dev/staging/prod mà không cần sửa code |
| Host / Port / Reload | `host="localhost"`, `port=8000`, `reload=True` | `HOST=0.0.0.0`, `PORT` từ env var, `reload=settings.debug` (`false`) | Trong container/cloud (Railway, Render) app phải lắng nghe `0.0.0.0` và cổng `PORT` do nền tảng cấp; tắt `reload` để ổn định và tiết kiệm CPU/RAM |
| Health & Readiness | Không có `/health`, `/ready` | Có `GET /health` (200 kèm uptime) và `GET /ready` (200 hoặc 503 khi chưa sẵn sàng) | Platform/load balancer biết khi nào container khởi động xong để route traffic (`/ready`) và khi nào app treo để restart (`/health`) |
| Logging | `print(...)`, in cả `OPENAI_API_KEY` | `logging` theo format JSON, không log secret | Log JSON dễ thu thập, tìm kiếm và lọc trong hệ thống observability (Loki, Datadog); không để lộ dữ liệu nhạy cảm vào log |
| Shutdown | Tắt đột ngột, không xử lý `SIGTERM` | `lifespan` (`is_ready = False`) + `signal.signal(signal.SIGTERM, ...)` | Khi deploy bản mới hoặc scale down, container nhận `SIGTERM` có thời gian hoàn tất request đang chạy thay vì làm lỗi client |
| Input & CORS | `POST /ask?question=...` qua query string, không cấu hình CORS | `POST /ask` nhận JSON body + validate 422, có `CORSMiddleware` cấu hình `ALLOWED_ORIGINS` | Body JSON chuẩn REST API cho payload dài và kiểm soát nguồn gốc trình duyệt được phép gọi API |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (image Python bản đầy đủ, dung lượng lớn vì chứa sẵn nhiều công cụ hệ thống/build).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước:** Để tận dụng **Docker layer cache**. Docker cache từng instruction từ trên xuống dưới; khi sửa code (`app.py`) mà không sửa `requirements.txt`, các layer cài dependencies phía trên vẫn giữ nguyên cache nên build lại rất nhanh.
4. **`CMD` vs `ENTRYPOINT`:**
   - `CMD` định nghĩa lệnh/tham số mặc định và **dễ dàng bị ghi đè** khi truyền lệnh ở cuối `docker run <image> <cmd>`.
   - `ENTRYPOINT` cố định executable chính của container; các tham số truyền thêm khi `docker run` sẽ trở thành argument cho `ENTRYPOINT` (chỉ bị ghi đè khi dùng cờ `--entrypoint`).

### Exercise 2.2: Build và chạy bản `develop`

Lệnh chạy:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name agent-dev -p 8000:8000 my-agent:develop
```

Output test container:
```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":4.8,"container":true}

$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`) và so sánh dung lượng

- **Stage 1 (`builder` — `python:3.11-slim`):** Cài build tools (`gcc`, `libpq-dev`) và `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime` — `python:3.11-slim`):** Tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` (các package đã cài), copy source `main.py` và `utils/mock_llm.py`, cấu hình `HEALTHCHECK`, chạy `uvicorn`.
- **Lý do image nhỏ hơn:** Không mang theo `python:3.11` full, `gcc`, `libpq-dev` hay cache build vào image cuối cùng, đồng thời tăng bảo mật nhờ chạy bằng user non-root `appuser`.

Kết quả đo trên máy (`docker images | grep my-agent`):
```text
my-agent:advanced       1f692e9773a2        240MB         57.4MB
my-agent:develop        63c52226f21b       1.67GB          426MB
```
- **Develop (`my-agent:develop`):** `1.67 GB` (~1670 MB; content size `426 MB`)
- **Production (`my-agent:advanced`):** `240 MB` (content size `57.4 MB`)
- **Chênh lệch:** Giảm `1430 MB`, tương đương **~85.6%** (`(1670 - 240) / 1670`)

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Kiến trúc các service:**

```text
Client ──(:80 / :443)──▶ Nginx (reverse proxy, rate limit 10r/s)
                             │
                             │  (network: internal - bridge)
                             ▼
                       Agent (FastAPI :8000)
                       ├──▶ Redis (redis:7-alpine :6379) — session & rate limit
                       └──▶ Qdrant (qdrant:v1.9.0 :6333) — vector DB
```

- **Cách giao tiếp:** Các service nằm trong cùng Docker bridge network `internal` và gọi nhau qua tên service (`agent:8000`, `redis:6379`, `qdrant:6333`). Chỉ `nginx` mở port `80`/`443` ra ngoài host; `agent`, `redis`, `qdrant` chỉ giao tiếp nội bộ. `agent` có `depends_on` chờ `redis` và `qdrant` đạt trạng thái `healthy` trước khi khởi động.

**Trạng thái stack (`docker compose -p k5-day14-docker ps`):**
```text
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED          STATUS                            PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     15 seconds ago   Up 3 seconds (health: starting)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     15 seconds ago   Up 3 seconds                      0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    15 seconds ago   Up 14 seconds (healthy)           6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     15 seconds ago   Up 14 seconds (healthy)           6379/tcp
```

**Kết quả test qua Nginx (`http://localhost`):**
```text
$ curl http://localhost/health
{"status":"ok","uptime_seconds":8.4,"version":"2.0.0","timestamp":"2026-11-26T07:40:41.602707"}

$ curl -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.2: Deploy Agent Part 6 lên Render

- **Public URL:** `https://k5-l3b-day14-vuthanh-2a202603930.onrender.com`
- **Cấu hình triển khai:** Render Web Service (`runtime: docker`, `rootDir: 06-lab-complete`, `region: singapore`, `plan: free`, `healthCheckPath: /health`) kết nối với Render Key Value (`redis`) qua biến môi trường `REDIS_URL` và `AGENT_API_KEY` đặt trực tiếp trên Render Dashboard.
- **Kết quả tự kiểm trên public URL:**
  - `GET /health` → `HTTP 200` (`{"status":"ok","environment":"production","uptime_seconds":34.4}`)
  - `GET /ready` → `HTTP 200` (`{"ready":true,"redis":"ok"}`)
  - `POST /ask` (không có `X-API-Key`) → `HTTP 401` (`{"detail":"Invalid or missing API key. Include header: X-API-Key: <your-key>"}`)
  - `POST /ask` (kèm `X-API-Key: $AGENT_API_KEY`) → `HTTP 200` (đã kiểm chứng đủ bộ 4 lệnh CP6 ra `200 / 200 / 401 / 200`)
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md)).

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (`03-cloud-deployment/railway/`) | `render.yaml` (`06-lab-complete/` & `03-cloud-deployment/render/`) |
| --- | --- | --- |
| **Định dạng & phạm vi** | **TOML**, cấu hình build/deploy cho **1 service**; các dịch vụ phụ như Redis tạo riêng trên Dashboard/CLI | **YAML (Infrastructure as Code / Blueprint)**, khai báo được **nhiều service cùng lúc** (Web Service + Redis `keyvalue`) và nối `REDIS_URL` tự động qua `fromService` |
| **Build & Start** | Dùng `[build] builder` (`NIXPACKS` hoặc `DOCKERFILE`), `[deploy] startCommand`, `healthcheckPath`, `healthcheckTimeout`, `restartPolicyType` | Khai báo `type: web`, `runtime` (`docker` hoặc `python`), `rootDir` (chọn thư mục con trong monorepo), `region`, `plan`, `healthCheckPath`, `autoDeploy` |
| **Biến môi trường & Secret** | Không liệt kê biến trong `railway.toml`; đặt qua Dashboard hoặc `railway variables set` | Cho phép khai báo `envVars` ngay trong YAML; secret bắt buộc dùng `sync: false` (nhập trên Dashboard) hoặc `generateValue: true` (tự sinh), không ghi giá trị thật vào Git |

### Exercise 3.3: Phân tích CI/CD Pipeline GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Pipeline trong `cloudbuild.yaml` tự động chạy 4 bước tuần tự khi push lên `main`, kết hợp cấu hình dịch vụ trong `service.yaml`:
1. **`test` (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`; nếu test lỗi thì dừng pipeline ngay.
2. **`build` (`gcr.io/cloud-builders/docker`):** Pull image `:latest` để tận dụng Docker layer cache (`--cache-from`), build Docker image gắn tag `$COMMIT_SHA` và `latest`.
3. **`push` (`gcr.io/cloud-builders/docker`):** Đẩy cả 2 tag image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Deploy bản mới nhất lên Cloud Run (`asia-southeast1`, `min-instances=1` tránh cold start, `max-instances=10`, `512Mi` RAM, `1` CPU) và gắn secret từ Secret Manager (`--set-secrets`); `service.yaml` mô tả cấu hình tương đương theo chuẩn Knative kèm `livenessProbe` (`/health`), `startupProbe` (`/ready`) và `containerConcurrency: 80`.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)

- **Kiểm tra API key ở đâu:** Dependency `verify_api_key` (dòng 39–54) đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)`, inject vào endpoint `POST /ask` (`Depends(verify_api_key)`), so sánh với `AGENT_API_KEY` từ biến môi trường (`os.getenv("AGENT_API_KEY", ...)`).
- **Khi thiếu hoặc sai key:** Thiếu header trả `401 Unauthorized`; sai key trong bản `develop` trả `403 Forbidden` (nên chuẩn hóa trả `401` khi thiếu/sai key ở Part 6).
- **Cách rotate key:** Đổi giá trị `AGENT_API_KEY` trong cấu hình biến môi trường trên nền tảng deploy rồi restart/rollout (hoặc hỗ trợ danh sách gồm key cũ + key mới trong giai đoạn chuyển tiếp trước khi thu hồi key cũ).

**Output test bản `develop` (`AGENT_API_KEY=secret-key-123`):**
```text
# Không có key -> 401
HTTP/1.1 401 Unauthorized
content-type: application/json
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key -> 200
HTTP/1.1 200 OK
content-type: application/json
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT flow (`auth.py`):** Client gửi `username`/`password` (`student`/`demo123`) tới `POST /auth/token` → server xác thực và ký JWT HS256 (`sub`, `role`, `iat`, `exp=60 phút`) → client gửi `Authorization: Bearer <TOKEN>` ở các request `/ask` → `verify_token` decode chữ ký, lấy `username`/`role` mà không cần query DB mỗi request.
- **Rate limiter (`rate_limiter.py`):**
  - **Algorithm:** **Sliding Window Counter** — dùng `collections.deque` lưu timestamp các request của từng `user_id`, xóa những timestamp cũ hơn `now - 60s` trước khi kiểm tra ngưỡng.
  - **Limit theo role:** `rate_limiter_user` = **10 requests/phút** (`student`); `rate_limiter_admin` = **100 requests/phút** (`teacher`). Vượt ngưỡng trả `429 Too Many Requests` kèm header `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` và `Retry-After`.
  - **Bypass / nâng hạn mức cho admin:** Dựa vào `role` giải mã từ JWT để chọn `rate_limiter_admin` (hoặc bỏ qua bước `limiter.check(...)` khi `role == "admin"`). Lưu ý bản demo đang lưu `deque` trong RAM nên khi scale nhiều instance cần chuyển sang **Redis** (như Part 6).

**Output test JWT + Rate limit (đã ẩn token qua biến `$TOKEN`):**
```text
# Request đầu có JWT -> 200 OK (kèm security headers)
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}

# Vòng lặp 12 request tiếp theo (1..9 trả 200 OK; từ request 10 vượt ngưỡng 10/phút -> 429)
=== Request 1 === HTTP/1.1 200 OK
...
=== Request 9 === HTTP/1.1 200 OK
=== Request 10 === HTTP/1.1 429 Too Many Requests
=== Request 11 === HTTP/1.1 429 Too Many Requests
=== Request 12 === HTTP/1.1 429 Too Many Requests

# Chi tiết response 429:
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795679058
retry-after: 45
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":45}}
```

### Exercise 4.4: Cost guard (`04-api-gateway/production/cost_guard.py`)

- **Cách hoạt động:**
  1. Trước khi gọi LLM, `check_budget(user_id)` kiểm tra 2 mức ngân sách theo ngày (`YYYY-MM-DD`): nếu vượt **global daily budget** (`$10.0/ngày`) trả `503`; nếu vượt **per-user daily budget** (`$1.0/ngày`) trả **`402 Payment Required`**; đạt ≥ 80% thì log warning.
  2. Sau khi LLM trả lời, `record_usage(user_id, input_tokens, output_tokens)` tính chi phí dựa trên đơn giá input/output tokens và cộng dồn vào usage của user và tổng hệ thống.
  3. **Production với Redis:** Thay `self._records` trong RAM bằng key Redis theo chu kỳ (ví dụ `budget:{user_id}:{YYYY-MM}` hoặc `{YYYY-MM-DD}`) dùng `INCRBYFLOAT` + `EXPIRE` để chia sẻ state giữa nhiều worker/instance và không mất dữ liệu khi restart.
- **Vì sao cần cả Rate limit và Cost guard:** Rate limit bảo vệ **tốc độ/lưu lượng** (chống spam/DDoS theo req/phút), nhưng không ngăn được việc user gửi ít request mà prompt/output rất dài làm đội chi phí LLM; Cost guard bảo vệ **ngân sách tiền** trực tiếp theo token/USD.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health checks & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt `/health` (Liveness) vs `/ready` (Readiness):**
  - `GET /health`: Kiểm tra process có còn sống không (uptime, trạng thái bộ nhớ qua `psutil`). Nếu fail → platform restart container.
  - `GET /ready`: Kiểm tra instance có sẵn sàng nhận traffic mới không (`_is_ready`, kết nối Redis/DB, số `_in_flight_requests`). Khi đang khởi động hoặc đang shutdown (`_is_ready = False`) trả `503 Service Unavailable` để Load Balancer ngừng đẩy request mới vào.
- **Graceful shutdown với `SIGTERM`:**
  - Khi gửi 2 request song song (mỗi request mất ~3s) và bắn `kill -SIGTERM 4347` sau `0.5s`:
    - Server nhận tín hiệu `15` (`SIGTERM`), chuyển trạng thái shutdown (`Waiting for connections to close`), **không cắt ngang** 2 request đang xử lý.
    - Cả 2 request đều trả về `HTTP/1.1 200 OK`, sau đó mới chạy `lifespan` shutdown (`🔄 Graceful shutdown initiated...` → `✅ Shutdown complete`) và thoát tiến trình an toàn.

**Output kiểm tra thực tế:**
```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":6.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:46:14.080117+00:00","checks":{"memory":{"status":"ok","used_percent":13.4}}}

$ curl http://localhost:8000/ready
{"ready":true,"in_flight_requests":1}

# Gửi 2 request song song + kill -SIGTERM 4347 sau 0.5s:
# Terminal 2 nhận đủ:
HTTP/1.1 200 OK
HTTP/1.1 200 OK
# Terminal 1 log:
INFO:     Shutting down
INFO:     127.0.0.1:38312 - "POST /ask?question=hello1 HTTP/1.1" 200 OK
INFO:     Waiting for connections to close. (CTRL+C to force quit)
INFO:     127.0.0.1:38326 - "POST /ask?question=hello2 HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO:     🔄 Graceful shutdown initiated...
INFO:     ✅ Shutdown complete
INFO:     Received signal 15 — uvicorn will handle graceful shutdown
```

### Exercise 5.3–5.5: Stateless Design, Redis Session & Load Balancing (`05-scaling-reliability/production/`)

- **Vì sao state trong RAM bị hỏng khi scale nhiều instance:** Mỗi container có bộ nhớ RAM riêng. Nếu lưu conversation history vào `dict` trong RAM, request 1 vào `instance-1` và request 2 qua Load Balancer vào `instance-2` sẽ không thấy lịch sử cũ. Khi chuyển state sang **Redis** (`session:{session_id}` với TTL 3600s), mọi instance đều đọc/ghi chung một nguồn state.
- **Trạng thái stack (`docker compose -p k5-day14-scaling ps`):** 3 container `agent` (`healthy`), 1 `redis:7-alpine` (`healthy`), 1 `nginx:alpine` (port `8080->80`).
- **Kết quả chạy `python test_stateless.py`:**
  - `Session ID`: `5ee8186e-2082-4954-b67c-8577058b4594`
  - 5 request liên tiếp đi qua **cả 3 instance khác nhau**: `instance-e7e531` (req 1, 4), `instance-966e31` (req 2, 5), `instance-cd87a7` (req 3).
  - Truy vấn `GET /chat/{session_id}/history` trả về đủ **`Total messages: 10`** (5 lượt hỏi + 5 lượt đáp), chứng minh Load Balancing phân tải đều và Redis giữ nguyên session xuyên suốt các instance.

---

## Part 6: Check Production Ready (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` trong Ubuntu WSL2 (`os.name = posix`, có Docker):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 42/42 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

- Kích thước Docker image đo thực tế: **63 MB** (`< 500 MB`), base `python:3.11-slim`, user non-root `appuser`.
- `docker stop`: **exit code 0, 0.6s** (`< 10s`).
- Không sửa `check_production_ready.py` hay `utils/mock_llm.py`.

---

## AI log
- **CP0:** Dùng AI hướng dẫn cài WSL2 trên máy Windows
- **CP1 (Part 1):** Dùng AI để giải thích các kết quả chạy của `01-localhost-vs-production/develop` và `production`, tổng hợp câu trả lời vào mục Part 1 của `MISSION_ANSWERS.md`. Đã tự chạy server, gửi request test cả 2 phiên bản và đối chiếu lại nội dung code trên máy
- **CP2 (Part 2 — Exercise 2.1–2.4):** Dùng AI giải thích 2 file dockerfile và nguyên nhân tại sao cần chia stage build(multi-stage build), tính % chênh lệch kích thước image từ kết quả đo thực tế (`1.67 GB` vs `240 MB`). Đã tự build image, khởi chạy stack Compose và test qua Nginx trên máy
- **CP3 (Part 4 — Exercise 4.1–4.4):** Dùng AI hướng dẫn lệnh test và tổng hợp giải thích tại sao cần rate-limiter, authJWT và cost guard. Đã tự chạy server, lấy JWT, test `401`/`200`/`429` và đối chiếu kết quả trên máy
- **CP4 (Part 5 — Exercise 5.1–5.5):** Dùng AI hướng dẫn lệnh test `SIGTERM`, khởi chạy stack 3 instance và tổng hợp giải thích vào Part 5 của `MISSION_ANSWERS.md`. Đã tự chạy server `develop` (Graceful shutdown), bật Docker Compose scale 3 agent + Redis + Nginx, chạy `test_stateless.py` và kiểm tra đủ 10 message qua cả 3 instance.
- **CP5 (Part 6 — `06-lab-complete/`):** Dùng AI hỗ trợ viết code các phần `TODO` trong `06-lab-complete/app/`, `Dockerfile`, `render.yaml`. Đã tự kiểm tra toàn bộ code bằng `python check_production_ready.py`, đạt `PASS 12/12` (`42/42 checks passed`, image `63 MB`)
``` text
python check_production_ready.py
  ⏳ Kiểm tra tĩnh: file, Dockerfile, compose, config, code...
  ⏳ Chuẩn bị Redis cho bài test stateless...
  ⏳ Khởi động agent: uvicorn app.main:app --workers 2 (Redis: container redis:7-alpine tạm thời)
  ⏳ Restart agent để kiểm tra stateless...
  ⏳ Kiểm tra readiness khi Redis mất kết nối...
  ⏳ Kiểm tra cost guard (budget ≈ 0)...
  ⏳ Kiểm tra graceful shutdown (SIGTERM)...
  ⏳ Build Docker image prod-check:86b03f58 (Docker 29.7.2) — lần đầu có thể mất vài phút...

================================================================
  Production Readiness Check — Day 14 Lab
================================================================

✅ 1. Dockerfile (multi-stage, < 500 MB)
     ✅ Dockerfile tồn tại
     ✅ requirements.txt tồn tại
     ✅ Multi-stage build (≥ 2 lệnh FROM)
     ✅ Base image gọn (slim / alpine / distroless) — stage cuối dùng python:3.11-slim
     ✅ Chạy bằng user non-root
     ✅ Có HEALTHCHECK
     ✅ Docker: build image thành công — 4s
     ✅ Docker: image < 500 MB — 63 MB
     ✅ Docker: container chạy được, GET /health → 200

✅ 2. docker-compose.yml (agent + redis)
     ✅ docker-compose.yml tồn tại
     ✅ Có service agent (build từ Dockerfile) + redis — services: agent, redis — đọc bằng docker compose config     
     ✅ Service agent kết nối redis (REDIS_URL + depends_on)

✅ 3. .dockerignore
     ✅ .dockerignore tồn tại và có nội dung
     ✅ .dockerignore loại trừ .env (secrets)
     ✅ .dockerignore loại trừ __pycache__, venv

✅ 4. Health check endpoint (GET /health)
     ✅ Code có route /health
     ✅ Khi chạy: GET /health → 200 — uvicorn --workers 2

✅ 5. Readiness endpoint (GET /ready)
     ✅ Code có route /ready
     ✅ Khi chạy: GET /ready → 200
     ✅ Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200)

✅ 6. API Key authentication
     ✅ Code đọc header X-API-Key
     ✅ Khi chạy: thiếu / sai API key → 401
     ✅ Khi chạy: API key đúng → 200

✅ 7. Rate limiting
     ✅ Code trả HTTP 429 khi vượt giới hạn
     ✅ Khi chạy: vượt giới hạn → 429 — 429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)
     ✅ Khi chạy: state nằm trong Redis — restart agent vẫn bị 429

✅ 8. Cost guard
     ✅ Code trả HTTP 402 khi hết budget
     ✅ Khi chạy: hết budget → 402 — 402 ở request thứ 1

✅ 9. Config từ environment variables
     ✅ app/config.py đọc biến môi trường
     ✅ .env.example liệt kê đủ biến cấu hình
     ✅ .env nằm trong .gitignore
     ✅ Không hard-code secret trong code
     ✅ Khi chạy: agent dùng AGENT_API_KEY và RATE_LIMIT_PER_MINUTE từ env

✅ 10. Structured logging
     ✅ Code ghi log dạng JSON
     ✅ Khi chạy: mọi dòng log của app là JSON hợp lệ — 12 dòng JSON

✅ 11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0
     ✅ Docker: `docker stop` tắt êm (exit code 0, < 10s) — exit code 0, 0.9s

✅ 12. Public URL ready (Railway / Render config)
     ✅ Có railway.toml hoặc render.yaml (không chỉ toàn comment)
     ✅ render.yaml: web service + healthCheckPath /health
     ✅ render.yaml: secret không ghi thẳng giá trị (generateValue / sync: false)
     ✅ App lắng nghe theo biến PORT do platform cấp

================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 42/42 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```
- **CP6 (Part 3 — Cloud Deployment):** Dùng AI hướng dẫn cấu hình Render Web Service + Key Value, tạo `DEPLOYMENT.md`, đã tự deploy lên Render và kiểm tra các endpoint public `/health`, `/ready`, `/ask`
- **CP7 (Part 7 Bước 1 — Benchmark local):** Dùng AI hỗ trợ bổ sung 2 mục còn thiếu (`security-02`, `scaling-03`) vào KNOWLEDGE_BASE trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py` khi đã đạt full test). Đã tự chạy toàn bộ `load_test.py` và `eval/run_eval.py` trên máy (`eval_v2_fixed.json` đạt `23/23`, 0 regression)
- **CP8 (Part 7 Bước 2 — Observability stack):** Dùng AI hỗ trợ giải thích phân tích log `trace_id` chậm nhất (`01e4fca4441ae5f6f2af5629b8b2e8a0`), kiểm tra số liệu CSV (`scale_1_stats.csv`, `scale_3_stats.csv`. Đã tự chạy Locust headless (1 vs 3 instances), kiểm tra Nginx chặn `/metrics` (404), mở Grafana, tìm trace chậm/lỗi trên Jaeger và thực hiện đủ 5 thí nghiệm phá hệ thống A–E với 4 alert cùng firing trên Prometheus
