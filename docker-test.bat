@echo off
REM Local Docker Testing Script for SEC Scraper
REM Run this to test before deploying to Railway

echo ===========================================
echo Building Docker image locally...
echo ===========================================
docker build -t sec-scraper-local .

if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED! Fix errors above.
    exit /b 1
)

echo.
echo ===========================================
echo Running container on http://localhost:8000
echo ===========================================
echo Press Ctrl+C to stop
echo.

docker run --rm -p 8000:7860 ^
    -e AUTH_USERNAME=admin ^
    -e AUTH_PASSWORD_HASH=a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3 ^
    -e FRONTEND_URL=http://localhost:8000 ^
    -e SESSION_SECRET=local-test-secret-key-12345 ^
    sec-scraper-local
