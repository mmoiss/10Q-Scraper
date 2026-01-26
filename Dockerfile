# Multi-stage build for SEC Scraper
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python requirements and install
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-builder /app/frontend/out ./static

# Railway provides PORT env variable
ENV PORT=8000

# Start server - use shell form to expand $PORT
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
