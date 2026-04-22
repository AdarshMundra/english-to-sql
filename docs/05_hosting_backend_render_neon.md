# Backend Hosting — Render + Neon.tech (Detailed Guide)

## Part 1: Neon.tech (PostgreSQL Database)

### What is Neon?
Neon is a serverless PostgreSQL provider. It separates storage from compute, which means:
- The database files live in object storage (always available)
- The compute (the Postgres process) sleeps after 5 minutes of inactivity and wakes on the next connection
- Free tier: 0.5 GB storage, 1 compute unit, 1 project

### Step 1: Create a Neon Project

1. Go to [console.neon.tech](https://console.neon.tech) and sign up (GitHub login works)
2. Click **New Project**
3. Choose a name (e.g. `text-to-sql`)
4. Select region closest to your Render deployment (e.g. `US East (Ohio)` for Render's `Oregon` — or match regions)
5. Click **Create Project**

Neon creates a default database named `neondb` and a default role named after your project.

### Step 2: Get Your Connection String

In the Neon console:
- Go to **Connection Details**
- Select **Connection string** format
- Toggle **Pooled connection** ON (recommended for web apps — uses PgBouncer)
- Copy the string — it looks like:

```
postgresql://neondb_owner:AbCdEf123@ep-quiet-pine-12345678.us-east-2.aws.neon.tech/neondb?sslmode=require
```

This is your `DB_CONNECTION_STRING`. Keep it secret — never commit it to git.

### Step 3: Load the Sample Schema (Optional)

If you want to use the college database for testing:

**Option A: Neon SQL Editor (browser)**
1. In the Neon console, click **SQL Editor**
2. Open `backend/college_schema.sql` from your project
3. Paste the entire contents and click **Run**

**Option B: psql from terminal**
```bash
psql "postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require" \
  -f backend/college_schema.sql
```

### Step 4: Verify the Connection Locally

```bash
cd backend
cp .env.example .env
# Edit .env and set DB_CONNECTION_STRING to your Neon connection string
python run.py "How many tables exist?" --db "postgresql://..."
```

Or test with psql:
```bash
psql "postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require" \
  -c "\dt"
```

### Neon Connection Details

| Setting | Value |
|---|---|
| Host | `ep-<project-id>.region.aws.neon.tech` |
| Port | `5432` |
| Database | `neondb` (default) |
| SSL | Required (`sslmode=require`) |
| Pooled host | `ep-<project-id>-pooler.region.aws.neon.tech` |

**Why use the pooled URL?** Neon's pooled endpoint (PgBouncer) handles many short-lived connections efficiently. FastAPI creates a new psycopg2 connection per request — pooling prevents exhausting Postgres connection limits.

### Neon Branches (Advanced)

Neon supports database branches (like git branches). This means you can:
- Create a `dev` branch for development testing
- Keep `main` branch for production data
- Branch and restore at any point in time

For this project, the `main` branch is sufficient.

---

## Part 2: Render (Backend API)

### What is Render?
Render is a cloud platform for deploying web services. For this project, it runs the FastAPI backend as a Python web service.

### Step 1: Prepare Your Repository

Ensure these files exist in your repo (they already do):

```
backend/
├── requirements.txt
├── api/main.py
└── .env.example   (never commit .env itself)
```

There is no `Procfile` or `render.yaml` required — you configure the start command in the Render dashboard.

### Step 2: Create a Render Web Service

1. Go to [dashboard.render.com](https://dashboard.render.com) and sign up
2. Click **New → Web Service**
3. Connect your GitHub account and select your repository
4. Configure the service:

| Field | Value |
|---|---|
| **Name** | `text-to-sql-api` (or any name) |
| **Region** | Closest to your users |
| **Branch** | `Production` (or `main`) |
| **Root Directory** | `backend` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free |

> **Root Directory:** Setting this to `backend` means Render treats the `backend/` folder as the project root. All commands run from there, and `requirements.txt` is found automatically.

5. Click **Create Web Service** (don't add environment variables yet — do it in the next step)

### Step 3: Set Environment Variables

In the Render dashboard → your service → **Environment**:

| Key | Value | Notes |
|---|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` | Required |
| `OPENAI_MODEL` | `gpt-4o` | Or `gpt-4o-mini` for lower cost |
| `DB_CONNECTION_STRING` | `postgresql://...@ep-....neon.tech/neondb?sslmode=require` | From Neon |
| `MAX_RETRIES` | `3` | Optional, 3 is the default |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | Optional |
| `EXECUTOR_MAX_ROWS` | `500` | Optional |
| `LOG_LEVEL` | `INFO` | Optional |

Mark `OPENAI_API_KEY` and `DB_CONNECTION_STRING` as **Secret** in Render's UI.

### Step 4: Trigger First Deploy

Render automatically deploys when you push to the connected branch. Or:
- In the Render dashboard → your service → **Manual Deploy → Deploy latest commit**

Watch the deploy log. A successful deploy shows:
```
==> Build successful
==> Starting service with 'uvicorn api.main:app --host 0.0.0.0 --port 10000'
INFO:     Started server process
INFO:     Application startup complete.
```

### Step 5: Verify Deployment

```bash
curl https://your-service.onrender.com/health
# → {"status":"ok","version":"3.0.0","openai_model":"gpt-4o"}
```

Open `https://your-service.onrender.com/docs` in a browser to see the Swagger UI.

Test a query:
```bash
curl -X POST https://your-service.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"english_query": "How many students per department?", "schema_source": "db", "execute_query": true}'
```

### Step 6: Fix CORS for Production (Recommended)

In `backend/api/main.py`, change the CORS middleware to restrict origins:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-app.vercel.app"],  # your Vercel URL
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Commit and push to trigger a redeploy.

---

## Render Free Tier Behaviour

### Sleep after inactivity
Free Render services sleep after **15 minutes** of no incoming requests. The first request after sleep has a **~30 second cold start** while Render boots the container.

**Solutions:**
- **Upgrade to Starter plan** ($7/month) — always-on
- **Uptime Robot (free)** — sends a ping to `/health` every 14 minutes, preventing sleep
  1. Sign up at uptimerobot.com
  2. Create monitor: HTTP(s), URL = `https://your-service.onrender.com/health`, every 14 min

### Build time
Free tier builds can take 3–5 minutes because `pip install` downloads all dependencies fresh.

**Speed tip:** Render caches pip packages between deploys if `requirements.txt` hasn't changed.

---

## Custom Domain (Optional)

In Render dashboard → your service → **Settings → Custom Domain**:
1. Add your domain (e.g. `api.yourdomain.com`)
2. Add the CNAME record shown by Render to your DNS provider
3. Wait for SSL certificate provisioning (~5 min)

Then update `VITE_API_URL` in Vercel to use `https://api.yourdomain.com`.

---

## Monitoring & Logs

### Render logs
- Dashboard → your service → **Logs**
- Shows uvicorn access logs + structlog output from the pipeline
- Each agent logs its start/complete with structlog's JSON format

### Neon monitoring
- Neon console → **Monitoring** tab
- Shows connections, query volume, compute time

---

## Connecting to Neon from Local Dev

Use the same `DB_CONNECTION_STRING` in your local `.env`:

```bash
# backend/.env
DB_CONNECTION_STRING=postgresql://neondb_owner:...@ep-....neon.tech/neondb?sslmode=require
```

Your local backend then uses the same database as production. For a separate dev database, use Neon's branch feature to create a `dev` branch and use its connection string locally.

---

## Common Issues

### `psycopg2.OperationalError: SSL connection is required`
Add `?sslmode=require` to the connection string.

### `connection timeout` on first query after inactivity
Neon compute waking up (1–2s) + Render cold start (if free tier). This is expected.

### `OPENAI_API_KEY not set`
Render environment variables are not automatically loaded from `.env` — they must be set in the dashboard.

### Build fails: `error: command 'gcc' failed`
psycopg2-binary includes a pre-compiled binary, so this shouldn't happen. If it does, ensure you're using `psycopg2-binary` not `psycopg2` in requirements.txt.

### `uvicorn: command not found`
Add `uvicorn[standard]` to requirements.txt (it's already there).

---

## Re-deployment Checklist

When pushing a new backend version:
- [ ] Environment variables in Render are up to date
- [ ] New dependencies added to `requirements.txt`
- [ ] CORS origins list updated if Vercel domain changed
- [ ] Database schema migrations applied to Neon if tables changed
- [ ] `/health` endpoint responds after deploy
