# SEC Filing Scraper

A secure web application to generate Excel spreadsheets with SEC 10-Q financial statements.

## Features

- 🔐 Password-protected access with session management
- 📊 Generates Excel files with Balance Sheet, Income Statement, Cash Flow, and Equity statements
- ⚡ Rate limiting to prevent abuse
- 🚀 Deploy with Vercel (frontend) + Railway (backend)

## Tech Stack

- **Frontend**: Next.js 16, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python, openpyxl
- **Data**: SEC EDGAR via edgartools

## Quick Start (Local Development)

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your credentials
python main.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 (default password: `secadmin123`)

## Production Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for complete step-by-step instructions for deploying to:
- **Frontend**: Vercel
- **Backend**: Railway

## Security

- Passwords are SHA256 hashed with timing-safe comparison
- Session tokens generated via `secrets.token_urlsafe`
- Rate limiting: 10 requests/minute per IP
- HttpOnly cookies with Secure flag in production
- CORS restricted to configured frontend URL

## Generate Password Hash

```bash
python -c "import hashlib; print(hashlib.sha256('your_password'.encode()).hexdigest())"
```

## License

Private - Authorized access only

