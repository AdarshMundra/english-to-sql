# Frontend Hosting — Vercel (Detailed Guide)

## What is Vercel?
Vercel is a frontend cloud platform optimised for Vite/React/Next.js deployments. It serves your built static files over a global CDN, handles SSL automatically, and rebuilds on every git push.

For this project, Vercel serves the React + Vite frontend. It does **not** run Python or the backend — that stays on Render.

---

## Prerequisites

- Your repository is on GitHub (this project uses the `Production` branch)
- The Render backend is already deployed and has a public URL
- Node 18+ installed locally

---

## Step 1: Build Locally (Verify First)

Before deploying, confirm the build works:

```bash
cd frontend
npm install
npm run build
```

Expected output:
```
dist/index.html
dist/assets/index-[hash].js
dist/assets/index-[hash].css
```

Check that `dist/index.html` exists. If the build errors, fix it before deploying.

---

## Step 2: Create a Vercel Project

1. Go to [vercel.com](https://vercel.com) and sign up (GitHub login recommended)
2. Click **Add New → Project**
3. **Import Git Repository** — find your repo
4. Configure the project:

| Setting | Value |
|---|---|
| **Framework Preset** | Vite (auto-detected) |
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` (auto-filled) |
| **Output Directory** | `dist` (auto-filled) |
| **Install Command** | `npm install` (auto-filled) |

> **Root Directory** is critical. Set it to `frontend` so Vercel looks for `package.json` in the right place. Without this, the build will fail because Vercel finds no `package.json` at the repo root.

5. Do **not** click Deploy yet — add environment variables first.

---

## Step 3: Set Environment Variables

In the Vercel project settings (or during import on the "Configure Project" screen):

| Key | Value | Environment |
|---|---|---|
| `VITE_API_URL` | `https://your-service.onrender.com` | Production |
| `VITE_API_URL` | `http://localhost:8000` | Development (optional) |

**Important:** The `VITE_` prefix is required — Vite only exposes variables with this prefix to client code at build time. Variables without this prefix are invisible to the browser.

**No trailing slash:** `https://your-service.onrender.com` not `https://your-service.onrender.com/`

---

## Step 4: Deploy

Click **Deploy**. Vercel will:
1. Clone your repo
2. `cd frontend`
3. `npm install`
4. `npm run build` (with your env vars baked in)
5. Serve the `dist/` folder on a global CDN

First deploy takes ~2–3 minutes. Watch the build log for errors.

Successful deploy output ends with:
```
✓ Build completed
✓ Deployed to https://your-app.vercel.app
```

---

## Step 5: Verify the Deployment

1. Open `https://your-app.vercel.app` in a browser
2. Check the header — `StatusBar` should show "API Online" + your model name
3. Go to Settings tab — confirm `VITE_API_URL` shows your Render URL
4. Run a test query in the Query tab

If `StatusBar` shows "API Unreachable":
- Check that Render is running (wait ~30s if it was sleeping)
- Verify `VITE_API_URL` is set correctly in Vercel
- Check browser console for CORS errors → fix backend CORS config

---

## Automatic Deployments (CI/CD)

By default, Vercel deploys on every push to your connected branch (`Production`).

**Vercel also creates Preview Deployments for pull requests:**
- Every PR gets a unique URL like `https://your-app-git-pr-5.vercel.app`
- Preview URLs use the same env vars as production (unless you configure per-env overrides)

To disable preview deployments: Vercel dashboard → Project Settings → Git → turn off "Deploy on Pull Request".

---

## Custom Domain (Optional)

1. Vercel dashboard → your project → **Settings → Domains**
2. Add your domain (e.g. `app.yourdomain.com`)
3. Vercel provides DNS records to add at your registrar:
   - **A record:** `76.76.21.21` (Vercel's IP)
   - or **CNAME:** `cname.vercel-dns.com` (for subdomains)
4. Vercel automatically provisions an SSL certificate via Let's Encrypt

After DNS propagates (~10–60 min), your app is live at your custom domain.

---

## Environment Variable Management

Vercel supports three environments for env vars:

| Environment | When used |
|---|---|
| **Production** | Deploys from your main/production branch |
| **Preview** | Pull request preview deployments |
| **Development** | `vercel dev` local development (optional) |

To update `VITE_API_URL` after your Render URL changes:
1. Vercel dashboard → Project → Settings → Environment Variables
2. Edit `VITE_API_URL` → save
3. Go to Deployments → click **Redeploy** on the latest deployment (or push a commit)

This is necessary because Vite bakes environment variables into the JS bundle at build time — you must rebuild for changes to take effect.

---

## Production vs Development .env Files

The project has:

```
frontend/.env                  # local dev (gitignored? check your .gitignore)
frontend/.env.example          # template committed to git
frontend/.env.production       # read by Vite during `npm run build`
```

`frontend/.env.production` content:
```
VITE_API_URL=https://your-service.onrender.com
```

However, for Vercel deployments, it's cleaner to set env vars in the Vercel dashboard and leave `.env.production` as a fallback or reference only. Vercel's dashboard env vars take precedence.

---

## SPA Routing Configuration

This app uses tab-based navigation managed in React state (no URL routing library). The `activeTab` state just conditionally renders components — there are no URL routes.

This means there is **no need** for a `vercel.json` rewrite rule. If you ever add `react-router-dom` with URL-based routes (e.g. `/query`, `/schema`), you would need:

```json
// vercel.json (at repo root or frontend/ root)
{
  "rewrites": [{ "source": "/(.*)", "destination": "/" }]
}
```

Without this, deep links would 404 on Vercel. For the current app, this is not needed.

---

## Build Output Details

After `npm run build`:

```
frontend/dist/
├── index.html              (~0.5 KB)
└── assets/
    ├── index-[hash].js     (~150 KB, all React + components)
    └── index-[hash].css    (~15 KB, all CSS Modules)
```

The hash in filenames is a content hash — if the file content changes, the hash changes, which busts browser cache automatically. Vercel serves these files with `Cache-Control: public, max-age=31536000, immutable`.

---

## Bandwidth & Speed

Vercel's free tier includes:
- 100 GB bandwidth/month
- Requests served from Vercel's edge network (CDN)
- Automatic Brotli/gzip compression

For a typical demo/personal app with ~100 users/day, bandwidth usage is <1 GB/month.

---

## Common Issues

### "Cannot find module" build error
Usually means `npm install` didn't run or `Root Directory` is set wrong. Confirm `Root Directory = frontend` in Vercel project settings.

### VITE_API_URL is `undefined` in the app
Variable must start with `VITE_`. Check Vercel dashboard → Environment Variables. Redeploy after adding.

### App loads but API calls fail (network error)
1. Verify Render service is running
2. Check browser console — CORS error? Update `allow_origins` in FastAPI
3. Verify `VITE_API_URL` has no trailing slash
4. Check that the Render URL matches exactly (http vs https)

### Old version still showing after code change
Vercel deploys are immutable. The new URL will be different. Hard-refresh (Ctrl+Shift+R) to clear browser cache.

### Build fails with "Cannot read VITE_API_URL of undefined"
The env var is not set in Vercel for the Production environment. Add it in Vercel dashboard and redeploy.

---

## Vercel CLI (Optional)

For faster iteration without git pushes:

```bash
npm install -g vercel

cd frontend
vercel login           # authenticate
vercel                 # deploy to preview URL
vercel --prod          # deploy to production
```

The CLI reads `.env.local` for local vars but uses Vercel dashboard vars for actual deployments.

---

## Redeploy Checklist

When the backend URL changes (e.g. Render service renamed):
- [ ] Update `VITE_API_URL` in Vercel dashboard (Production environment)
- [ ] Trigger a redeploy in Vercel (or push a commit)
- [ ] Verify `StatusBar` shows "API Online" after redeploy
- [ ] If using custom domain: ensure it still points to the correct Vercel project

When frontend code changes:
- [ ] `npm run build` locally to verify no build errors
- [ ] Push to `Production` branch
- [ ] Vercel auto-deploys within ~2 minutes
- [ ] Verify the new deployment at `https://your-app.vercel.app`
