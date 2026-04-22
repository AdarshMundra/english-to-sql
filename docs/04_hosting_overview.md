# Hosting Overview — Vercel + Render + Neon.tech

## Architecture Summary

```
Browser
   │
   │  HTTPS
   ▼
Vercel (Frontend)          ← React + Vite static build
   │
   │  HTTPS API calls
   ▼
Render (Backend API)       ← FastAPI + Python (uvicorn)
   │
   │  PostgreSQL wire protocol
   ▼
Neon.tech (Database)       ← Serverless PostgreSQL
```

---

## Service Roles

| Service | What runs there | Free tier |
|---|---|---|
| **Vercel** | React frontend (`npm run build` output) | Yes — unlimited static sites |
| **Render** | FastAPI backend (`uvicorn api.main:app`) | Yes — 750 hrs/month (sleeps after 15 min inactivity) |
| **Neon.tech** | PostgreSQL database | Yes — 0.5 GB storage, 1 compute unit |

---

## Environment Variables at a Glance

### Render (Backend)
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
DB_CONNECTION_STRING=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
MAX_RETRIES=3
SCHEMA_CACHE_TTL_SECONDS=3600
EXECUTOR_MAX_ROWS=500
LOG_LEVEL=INFO
```

### Vercel (Frontend)
```
VITE_API_URL=https://your-backend.onrender.com
```

---

## Deployment Workflow

```
1. Push code to GitHub
        │
        ├──→ Vercel auto-deploys frontend  (Build: npm run build, Output: dist/)
        └──→ Render auto-deploys backend   (Start: uvicorn api.main:app --host 0.0.0.0 --port $PORT)
```

Both services connect to GitHub and redeploy on every push to your production branch.

---

## Critical Configuration Points

### Backend → Neon.tech
- Connection string must include `?sslmode=require`
- Neon provides a pooled connection URL (use the **pooled** URL for better concurrency)
- Set `DB_CONNECTION_STRING` in Render environment variables — **never** hard-code it

### Frontend → Backend
- Set `VITE_API_URL` in Vercel to the exact Render URL (no trailing slash)
- The value is baked into the JS bundle at build time — change it in Vercel, then trigger a redeploy

### CORS
- Backend currently allows `allow_origins=["*"]`
- For production, restrict to your Vercel domain: `allow_origins=["https://your-app.vercel.app"]`

---

## Free Tier Limitations

| Service | Limitation | Impact |
|---|---|---|
| Render | Web service sleeps after 15 min inactivity | First request after sleep takes ~30s to respond |
| Neon.tech | Compute suspends after 5 min inactivity | First query after suspend adds ~1–2s cold start |
| Vercel | 100 GB bandwidth/month | Sufficient for personal/demo use |

To avoid Render sleep: upgrade to a paid plan, or use an external cron to ping `/health` every 14 minutes.

---

## Quick Reference: URLs After Deployment

| Resource | URL pattern |
|---|---|
| Frontend | `https://your-app.vercel.app` |
| Backend API | `https://your-service.onrender.com` |
| Swagger UI | `https://your-service.onrender.com/docs` |
| Health check | `https://your-service.onrender.com/health` |
| Neon Console | `https://console.neon.tech` |
