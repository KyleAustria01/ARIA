# ARIA — Free Deployment Guide

**Stack:** Render (backend) + Upstash (Redis) + Vercel (frontend)  
All tiers are 100% free, no credit card required except Render (for verification only, never charged on free tier).

---

## Step 1 — Upstash Redis (free Redis)

1. Go to **https://upstash.com** → Sign up free
2. Create database → **Redis** → region closest to you → **Free** plan
3. Copy the **Redis URL** (`rediss://default:...`) from the dashboard  
   _(it starts with `rediss://` — the extra `s` means TLS, required by Upstash)_

---

## Step 2 — Render (backend)

1. Go to **https://render.com** → Sign up with GitHub (free)
2. **New → Web Service** → Connect your GitHub repo
3. Render will auto-detect `render.yaml` — click **Apply**
4. In the service settings → **Environment** tab, add these variables:

| Variable              | Value                                           |
| --------------------- | ----------------------------------------------- |
| `REDIS_URL`           | Your Upstash `rediss://...` URL                 |
| `FRONTEND_URL`        | Your Vercel URL (fill in after Step 3)          |
| `CEREBRAS_API_KEY`    | From https://cloud.cerebras.ai (free)           |
| `GROQ_API_KEY`        | From https://console.groq.com (free)            |
| `GEMINI_API_KEY`      | From https://aistudio.google.com (free)         |
| `ELEVENLABS_API_KEY`  | From https://elevenlabs.io (free 10k chars/mo)  |
| `ELEVENLABS_VOICE_ID` | Leave default or pick from ElevenLabs dashboard |
| `TAVILY_API_KEY`      | From https://tavily.com (free 1k searches/mo)   |

5. Deploy → wait for the build to finish (5–10 min first time)
6. Copy your backend URL — it looks like: `https://aria-backend.onrender.com`

> **Note:** Free Render services sleep after 15 min of inactivity.  
> First request after sleep takes ~30s to wake up. This is a free-tier limitation.

---

## Step 3 — Vercel (frontend)

1. Go to **https://vercel.com** → Sign up with GitHub (free)
2. **New Project** → Import your GitHub repo → set **Root Directory** to `frontend`
3. Vercel auto-detects Vite. Keep defaults.
4. Add one **Environment Variable** in Project Settings → Environment Variables:

| Variable      | Value                                                                             |
| ------------- | --------------------------------------------------------------------------------- |
| `VITE_WS_URL` | `wss://aria-backend.onrender.com` _(your Render URL, replace `https` with `wss`)_ |

5. **Deploy** → Vercel builds and gives you a URL like `https://aria-xyz.vercel.app`

---

## Step 4 — Cross-link the two services

1. In Render dashboard → **aria-backend** → Environment → update `FRONTEND_URL` to your Vercel URL
2. In `frontend/vercel.json` → replace `REPLACE_WITH_YOUR_RENDER_URL` with your actual Render URL:
   ```
   "destination": "https://aria-backend.onrender.com/api/:path*"
   ```
3. Push the change → Vercel redeploys automatically

---

## Free Tier Limits

| Service       | Free Limit                                       |
| ------------- | ------------------------------------------------ |
| Render        | 750 hrs/month · 512 MB RAM · sleeps after 15 min |
| Upstash Redis | 10,000 commands/day · 256 MB storage             |
| Vercel        | Unlimited deploys · 100 GB bandwidth/month       |
| ElevenLabs    | 10,000 chars/month TTS                           |
| Groq          | 14,400 requests/day (Whisper STT + LLM)          |
| Gemini        | 1,500 requests/day                               |
| Tavily        | 1,000 searches/month                             |

---

## Local Development (unchanged)

```bash
# Backend
cd C:\Users\austria\Documents\AI
.\backend\venv\Scripts\activate
python -m uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend
npm run dev
```

The Vite dev proxy (`vite.config.ts`) automatically forwards `/api/*` and `/ws/*` to `localhost:8000` — no env vars needed locally.
