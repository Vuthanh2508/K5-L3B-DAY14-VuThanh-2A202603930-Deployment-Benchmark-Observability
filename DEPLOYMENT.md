# Deployment Information

## Public URL
https://k5-l3b-day14-vuthanh-2a202603930.onrender.com

## Platform
Render (Web Service — Docker, Root Directory: `06-lab-complete`, kết nối Render Key Value Redis)

## Test Commands

### 1. Health Check (Liveness)
```bash
curl -i https://k5-l3b-day14-vuthanh-2a202603930.onrender.com/health
# Expected: HTTP 200 -> {"status":"ok","environment":"production",...}
```

### 2. Readiness Check (Redis connection)
```bash
curl -i https://k5-l3b-day14-vuthanh-2a202603930.onrender.com/ready
# Expected: HTTP 200 -> {"ready":true,"redis":"ok"}
```

### 3. API Test (không có key → 401)
```bash
curl -i -X POST https://k5-l3b-day14-vuthanh-2a202603930.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: HTTP 401
```

### 4. API Test (có API Key → 200)
```bash
curl -i -X POST https://k5-l3b-day14-vuthanh-2a202603930.onrender.com/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: HTTP 200
```

## Environment Variables Set
- `AGENT_API_KEY` *(cấu hình bảo mật trên Render Dashboard, không commit lên Git)*
- `REDIS_URL` *(Internal Key Value URL của Render Redis)*
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
