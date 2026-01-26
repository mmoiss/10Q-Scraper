# Deployment Guide

Complete guide for deploying SEC Filing Scraper to production using **Vercel** (frontend) and **Railway** (backend).

---

## Prerequisites

- GitHub repository with this codebase
- [Vercel account](https://vercel.com) (free tier works)
- [Railway account](https://railway.app) (free tier works)
- A strong password for the admin account

---

## Step 1: Generate Password Hash

Before deploying, generate a SHA256 hash of your password:

```bash
python -c "import hashlib; print(hashlib.sha256('YOUR_PASSWORD_HERE'.encode()).hexdigest())"
```

**Save this hash** – you'll need it for Railway configuration.

---

## Step 2: Deploy Backend to Railway

1. **Create Project**
   - Go to [railway.app](https://railway.app) → "New Project"
   - Select "Deploy from GitHub repo"
   - Connect your GitHub account and select this repository

2. **Configure Root Directory**
   - Go to Settings → Root Directory
   - Set to: `backend`

3. **Add Environment Variables**
   In Settings → Variables, add:

   | Variable | Value |
   |----------|-------|
   | `AUTH_USERNAME` | Your admin username (e.g., `admin`) |
   | `AUTH_PASSWORD_HASH` | SHA256 hash from Step 1 |
   | `SESSION_SECRET` | Random 64-char hex string* |
   | `FRONTEND_URL` | `https://your-app.vercel.app` (set after Vercel deploy) |

   *Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`

4. **Deploy**
   - Railway auto-deploys on push
   - Note your Railway URL (e.g., `https://your-app.up.railway.app`)

---

## Step 3: Deploy Frontend to Vercel

1. **Create Project**
   - Go to [vercel.com](https://vercel.com) → "Add New Project"
   - Import your GitHub repository

2. **Configure Root Directory**
   - Set Root Directory to: `frontend`

3. **Add Environment Variable**

   | Variable | Value |
   |----------|-------|
   | `NEXT_PUBLIC_API_URL` | Your Railway URL from Step 2 |

4. **Deploy**
   - Click "Deploy"
   - Note your Vercel URL (e.g., `https://your-app.vercel.app`)

---

## Step 4: Update Railway CORS

Go back to Railway and update `FRONTEND_URL` with your actual Vercel URL:

```
FRONTEND_URL=https://your-app.vercel.app
```

Redeploy Railway for changes to take effect.

---

## Environment Variables Reference

### Backend (Railway)

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_USERNAME` | Yes | Login username |
| `AUTH_PASSWORD_HASH` | Yes | SHA256 hash of password |
| `SESSION_SECRET` | Yes | Random hex string for sessions |
| `FRONTEND_URL` | Yes | Vercel frontend URL (for CORS) |

### Frontend (Vercel)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Railway backend URL |

---

## Troubleshooting

### "Authentication required" errors
- Verify `FRONTEND_URL` matches your exact Vercel domain
- Check that cookies are enabled in your browser
- Ensure both URLs use HTTPS

### CORS errors
- `FRONTEND_URL` must match Vercel URL exactly (no trailing slash)
- Redeploy Railway after changing CORS settings

### 500 errors on generate
- Check Railway logs for Python errors
- Ensure all environment variables are set

---

## Security Notes

- Never commit `.env` files to version control
- Rotate `SESSION_SECRET` periodically
- Use a strong password (12+ characters)
- All passwords are hashed with SHA256 before comparison
- Rate limiting is enabled (10 requests/minute per IP)
