from dotenv import load_dotenv
load_dotenv()  # Load .env file before other imports use os.getenv

from fastapi import FastAPI, HTTPException, Depends, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import pathlib
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
import threading
import uuid


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

# Job storage for background processing
jobs: dict[str, dict] = {}
JOB_EXPIRY = timedelta(hours=1)


# ============== CORS CONFIGURATION ==============
# For same-origin deployment, we only need localhost for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:8000",
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
    # Debug logging
    print(f"[AUTH DEBUG] Session token received: {token[:10]}..." if token else "[AUTH DEBUG] No session token")
    print(f"[AUTH DEBUG] All cookies: {list(request.cookies.keys())}")
    print(f"[AUTH DEBUG] Active sessions: {len(sessions)}")
    if not verify_session(token):
        print(f"[AUTH DEBUG] Session verification FAILED")
        raise HTTPException(status_code=401, detail="Authentication required")
    print(f"[AUTH DEBUG] Session verification OK")
    return token


# ============== BACKGROUND JOB PROCESSING ==============
import gc  # For manual garbage collection

BATCH_SIZE = 5  # Process 5 filings at a time to stay within 1GB RAM


def process_job(job_id: str, name: str, email: str, ticker: str):
    """Process SEC data in background thread with batch processing for memory efficiency."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["message"] = "Setting up SEC identity..."
        
        # Set identity for SEC Edgar API
        identity = f"{name} {email}"
        print(f"[{datetime.now()}] Job {job_id}: Setting identity to: {identity}")
        edgar.set_identity(identity)
        
        # Fetch company data
        jobs[job_id]["message"] = f"Fetching company data for {ticker}..."
        print(f"[{datetime.now()}] Job {job_id}: Fetching company: {ticker}")
        
        try:
            company = edgar.Company(ticker.upper())
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = f"Invalid company ticker: {ticker}. Please check the ticker symbol and try again."
            return
        
        # Fetch 10-Q filings
        jobs[job_id]["message"] = "Fetching 10-Q filings since 2010..."
        print(f"[{datetime.now()}] Job {job_id}: Fetching filings since 2010...")
        all_filings = company.get_filings(form="10-Q").filter(date="2010-01-01:")
        total_filings = len(all_filings)
        print(f"[{datetime.now()}] Job {job_id}: Found {total_filings} total filings")
        
        if total_filings == 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = f"No 10-Q filings found for {ticker} since 2010."
            return
        
        # Process filings in batches to prevent memory exhaustion
        # Each batch: parse XBRL -> extract DataFrames -> append to lists -> clear memory
        all_bs_dfs = []
        all_is_dfs = []
        all_cf_dfs = []
        all_se_dfs = []
        
        num_batches = (total_filings + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, total_filings)
            batch_filings = all_filings[start_idx:end_idx]
            
            jobs[job_id]["message"] = f"Processing batch {batch_idx + 1}/{num_batches} ({start_idx + 1}-{end_idx} of {total_filings} filings)..."
            print(f"[{datetime.now()}] Job {job_id}: Processing batch {batch_idx + 1}/{num_batches} (filings {start_idx + 1}-{end_idx})")
            
            try:
                # Parse XBRL for this batch
                xbrls = edgar.xbrl.XBRLS.from_filings(batch_filings)
                statements = xbrls.statements
                batch_size = len(batch_filings)
                
                # Extract DataFrames for this batch
                try:
                    bs_df = statements.balance_sheet(max_periods=batch_size).to_dataframe()
                    all_bs_dfs.append(bs_df)
                except Exception as e:
                    print(f"[{datetime.now()}] Job {job_id}: Batch {batch_idx + 1} - Balance sheet error: {e}")
                
                try:
                    is_df = statements.income_statement(max_periods=batch_size).to_dataframe()
                    all_is_dfs.append(is_df)
                except Exception as e:
                    print(f"[{datetime.now()}] Job {job_id}: Batch {batch_idx + 1} - Income statement error: {e}")
                
                try:
                    cf_df = statements.cashflow_statement(max_periods=batch_size).to_dataframe()
                    all_cf_dfs.append(cf_df)
                except Exception as e:
                    print(f"[{datetime.now()}] Job {job_id}: Batch {batch_idx + 1} - Cash flow error: {e}")
                
                try:
                    se_df = statements.statement_of_equity(max_periods=batch_size).to_dataframe()
                    all_se_dfs.append(se_df)
                except Exception as e:
                    print(f"[{datetime.now()}] Job {job_id}: Batch {batch_idx + 1} - Equity statement error: {e}")
                
                # Clear memory after each batch
                del xbrls, statements
                gc.collect()
                print(f"[{datetime.now()}] Job {job_id}: Batch {batch_idx + 1} complete, memory cleared")
                
            except Exception as e:
                print(f"[{datetime.now()}] Job {job_id}: Error in batch {batch_idx + 1}: {e}")
                traceback.print_exc()
                # Continue with other batches even if one fails
                continue
        
        # Check if we got any data
        if not all_bs_dfs and not all_is_dfs and not all_cf_dfs and not all_se_dfs:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Failed to extract any financial data from filings."
            return
        
        # Concatenate all batch results
        jobs[job_id]["message"] = "Combining batched results..."
        print(f"[{datetime.now()}] Job {job_id}: Concatenating {len(all_bs_dfs)} batch results...")
        
        # Concatenate DataFrames horizontally (columns = periods)
        BS = pd.concat(all_bs_dfs, axis=1) if all_bs_dfs else pd.DataFrame()
        IS = pd.concat(all_is_dfs, axis=1) if all_is_dfs else pd.DataFrame()
        CF = pd.concat(all_cf_dfs, axis=1) if all_cf_dfs else pd.DataFrame()
        SE = pd.concat(all_se_dfs, axis=1) if all_se_dfs else pd.DataFrame()
        
        # Clear batch lists
        del all_bs_dfs, all_is_dfs, all_cf_dfs, all_se_dfs
        gc.collect()
        
        # Create Excel file
        jobs[job_id]["message"] = "Creating Excel file..."
        print(f"[{datetime.now()}] Job {job_id}: Creating Excel file...")
        
        BS_ROW = 0
        IS_ROW = len(BS) + 2
        CF_ROW = IS_ROW + len(IS) + 1
        SE_ROW = CF_ROW + len(CF) + 1
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if not BS.empty:
                BS.to_excel(writer, sheet_name='Combined', startrow=BS_ROW, index=False)
            if not IS.empty:
                IS.to_excel(writer, sheet_name='Combined', startrow=IS_ROW, index=False, header=False)
            if not CF.empty:
                CF.to_excel(writer, sheet_name='Combined', startrow=CF_ROW, index=False, header=False)
            if not SE.empty:
                SE.to_excel(writer, sheet_name='Combined', startrow=SE_ROW, index=False, header=False)
        
        output.seek(0)
        
        # Store result
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"Report ready! Processed {total_filings} filings."
        jobs[job_id]["result"] = output.getvalue()
        jobs[job_id]["filename"] = f"{ticker.upper()}_10Q_Financials.xlsx"
        print(f"[{datetime.now()}] Job {job_id}: Completed successfully with {total_filings} filings")
        
    except Exception as e:
        print(f"[{datetime.now()}] Job {job_id}: Global error: {e}")
        traceback.print_exc()
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = f"An unexpected error occurred: {str(e)}"


def cleanup_expired_jobs():
    """Remove expired jobs from storage."""
    now = datetime.now(timezone.utc)
    expired = [
        job_id for job_id, job in jobs.items()
        if now > job.get("expires_at", now)
    ]
    for job_id in expired:
        del jobs[job_id]


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
    print(f"[AUTH DEBUG] Login successful for {login_data.username}, created session token: {token[:10]}...")
    
    # Determine if we're in production (HTTPS)
    is_production = FRONTEND_URL.startswith("https://")
    print(f"[AUTH DEBUG] Is production: {is_production}, FRONTEND_URL: {FRONTEND_URL}")
    
    # Set cookie with appropriate security settings
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=is_production,  # Only require HTTPS in production
        samesite="lax",  # Same-origin deployment, lax is fine
        path="/",  # Ensure cookie is sent for all routes
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
async def generate_excel(
    request: Request,
    data: GenerateRequest,
    _token: str = Depends(require_auth)
):
    """Start background job to generate Excel file. Returns job ID for polling."""
    client_ip = get_client_ip(request)
    print(f"[{datetime.now()}] Starting generation for {data.ticker} by {data.email} from {client_ip}")
    
    # Rate limit API requests
    if not check_rate_limit(f"generate_{client_ip}"):
        print(f"[{datetime.now()}] Rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait before making another request."
        )
    
    # Cleanup expired jobs
    cleanup_expired_jobs()
    
    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "message": "Starting job...",
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + JOB_EXPIRY,
        "ticker": data.ticker.upper(),
    }
    
    # Start background thread
    thread = threading.Thread(
        target=process_job,
        args=(job_id, data.name, data.email, data.ticker)
    )
    thread.start()
    
    return {"job_id": job_id, "status": "pending", "message": "Job started"}


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str, request: Request, _token: str = Depends(require_auth)):
    """Check the status of a background job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "message": job.get("message", ""),
        "error": job.get("error"),
    }


@app.get("/api/job/{job_id}/download")
async def download_job_result(job_id: str, request: Request, _token: str = Depends(require_auth)):
    """Download the result of a completed job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    
    if "result" not in job:
        raise HTTPException(status_code=500, detail="Result not available")
    
    # Return file
    output = io.BytesIO(job["result"])
    filename = job.get("filename", "report.xlsx")
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ============== STATIC FILES ==============
# Mount static files AFTER all API routes (order matters!)
# This serves the Next.js static export
static_dir = pathlib.Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # Added timeout_keep_alive to help with connection drops
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=120)
