from dotenv import load_dotenv
load_dotenv()  # Load .env file before other imports use os.getenv

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import edgar
import pandas as pd
import io
import traceback
import hashlib
import secrets
import os
from collections import defaultdict
import time


app = FastAPI(title="SEC Scraper API")

# ============== CONFIGURATION ==============
# Set these as environment variables in production
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Password hash - REQUIRED in production, fallback for local dev only
_default_hash = hashlib.sha256("secadmin123".encode()).hexdigest()
_env_hash = os.getenv("AUTH_PASSWORD_HASH")
if not _env_hash and FRONTEND_URL != "http://localhost:3000":
    raise ValueError("AUTH_PASSWORD_HASH environment variable is required in production")
AUTH_PASSWORD_HASH = _env_hash or _default_hash

# Session storage (in production, use Redis or database)
sessions: dict[str, datetime] = {}
SESSION_DURATION = timedelta(hours=24)

# Rate limiting storage
rate_limit_storage: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 10  # requests
RATE_LIMIT_WINDOW = 60  # seconds


# ============== CORS CONFIGURATION ==============
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://10-q-scraper.vercel.app",
        "https://10-q-scraper.vercel.app/",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== MODELS ==============
class GenerateRequest(BaseModel):
    name: str
    email: EmailStr
    ticker: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ============== RATE LIMITING ==============
def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    rate_limit_storage[client_ip] = [
        t for t in rate_limit_storage[client_ip] if t > window_start
    ]
    
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False
    
    rate_limit_storage[client_ip].append(now)
    return True


def get_client_ip(request: Request) -> str:
    """Get client IP, considering proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ============== AUTHENTICATION ==============
def verify_password(password: str) -> bool:
    """Verify password against stored hash."""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return secrets.compare_digest(password_hash, AUTH_PASSWORD_HASH)


def create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    sessions[token] = datetime.now(timezone.utc) + SESSION_DURATION
    return token


def verify_session(token: str | None) -> bool:
    """Verify if session token is valid."""
    if not token:
        return False
    
    expiry = sessions.get(token)
    if not expiry:
        return False
    
    if datetime.now(timezone.utc) > expiry:
        # Session expired, remove it
        del sessions[token]
        return False
    
    return True


def get_session_token(request: Request) -> str | None:
    """Extract session token from cookie."""
    return request.cookies.get("session_token")


async def require_auth(request: Request):
    """Dependency to require authentication."""
    token = get_session_token(request)
    if not verify_session(token):
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


# ============== ENDPOINTS ==============
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/login")
async def login(request: Request, login_data: LoginRequest, response: Response):
    """Authenticate user and create session."""
    client_ip = get_client_ip(request)
    
    # Rate limit login attempts
    if not check_rate_limit(f"login_{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later."
        )
    
    # Verify credentials
    if login_data.username != AUTH_USERNAME or not verify_password(login_data.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # Create session
    token = create_session()
    
    # Determine if we're in production (HTTPS)
    is_production = FRONTEND_URL.startswith("https://")
    
    # Set cookie with appropriate security settings
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=is_production,  # Only require HTTPS in production
        samesite="none" if is_production else "lax",  # 'none' required for cross-origin cookies
        max_age=int(SESSION_DURATION.total_seconds()),
    )
    
    return {"success": True, "message": "Login successful"}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    """Logout and invalidate session."""
    token = get_session_token(request)
    if token and token in sessions:
        del sessions[token]
    
    response.delete_cookie("session_token")
    return {"success": True, "message": "Logged out"}


@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check if user is authenticated."""
    token = get_session_token(request)
    is_authenticated = verify_session(token)
    return {"authenticated": is_authenticated}


@app.post("/api/generate")
def generate_excel(
    request: Request,
    data: GenerateRequest,
    _token: str = Depends(require_auth)
):
    """Generate an Excel file with SEC 10-Q financial statements."""
    client_ip = get_client_ip(request)
    print(f"[{datetime.now()}] Starting generation for {data.ticker} by {data.email} from {client_ip}")
    
    # Rate limit API requests
    if not check_rate_limit(f"generate_{client_ip}"):
        print(f"[{datetime.now()}] Rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait before making another request."
        )
    
    try:
        # Set identity for SEC Edgar API
        identity = f"{data.name} {data.email}"
        print(f"[{datetime.now()}] Setting identity to: {identity}")
        edgar.set_identity(identity)
        
        # Fetch company data
        try:
            print(f"[{datetime.now()}] Fetching company: {data.ticker}")
            company = edgar.Company(data.ticker.upper())
            print(f"[{datetime.now()}] Company fetched: {company}")
        except Exception as e:
            print(f"[{datetime.now()}] Error fetching company: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid company ticker: {data.ticker}. Please check the ticker symbol and try again."
            )
        
        # Fetch 10-Q filings
        try:
            print(f"[{datetime.now()}] Fetching filings since 2010...")
            filings = company.get_filings(form="10-Q").filter(date="2010-01-01:")
            print(f"[{datetime.now()}] Found {len(filings)} filings")
            
            if len(filings) == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No 10-Q filings found for {data.ticker} since 2010."
                )
            
            print(f"[{datetime.now()}] Parsing XBRL data (this may take a while)...")
            xbrls = edgar.xbrl.XBRLS.from_filings(filings)
            print(f"[{datetime.now()}] XBRL parsed. Stitching statements...")
            stitched_statements = xbrls.statements
            print(f"[{datetime.now()}] Statements stitched.")
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"[{datetime.now()}] Error in Edgar processing: {e}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching filings: {str(e)}"
            )
        
        # Generate financial statements DataFrames
        available_periods = len(filings)
        print(f"[{datetime.now()}] Converting to DataFrames ({available_periods} periods)...")
        
        try:
            BS = stitched_statements.balance_sheet(max_periods=available_periods).to_dataframe()
            print(f"[{datetime.now()}] Balance Sheet generated")
            IS = stitched_statements.income_statement(max_periods=available_periods).to_dataframe()
            print(f"[{datetime.now()}] Income Statement generated")
            CF = stitched_statements.cashflow_statement(max_periods=available_periods).to_dataframe()
            print(f"[{datetime.now()}] Cash Flow generated")
            SE = stitched_statements.statement_of_equity(max_periods=available_periods).to_dataframe()
            print(f"[{datetime.now()}] Equity Statement generated")
        except Exception as e:
            print(f"[{datetime.now()}] Error generating DataFrames: {e}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error processing financial statements: {str(e)}"
            )
        
        # Calculate row positions for combined sheet
        BS_ROW = 0
        IS_ROW = len(BS) + 2
        CF_ROW = IS_ROW + len(IS) + 1
        SE_ROW = CF_ROW + len(CF) + 1
        
        # Create Excel file in memory
        print(f"[{datetime.now()}] Writing to Excel...")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            BS.to_excel(writer, sheet_name='Combined', startrow=BS_ROW, index=False)
            IS.to_excel(writer, sheet_name='Combined', startrow=IS_ROW, index=False, header=False)
            CF.to_excel(writer, sheet_name='Combined', startrow=CF_ROW, index=False, header=False)
            SE.to_excel(writer, sheet_name='Combined', startrow=SE_ROW, index=False, header=False)
        
        output.seek(0)
        print(f"[{datetime.now()}] Excel created. Size: {output.getbuffer().nbytes} bytes. Returning response.")
        
        # Return as downloadable file
        filename = f"{data.ticker.upper()}_10Q_Financials.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[{datetime.now()}] Global error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    # Added timeout_keep_alive to help with connection drops
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=120)
