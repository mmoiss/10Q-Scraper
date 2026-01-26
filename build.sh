#!/bin/bash
set -e

echo "=== Building SEC Scraper for Railway ==="

# Install frontend dependencies and build
echo "Building frontend..."
cd frontend
npm ci
npm run build

# Copy static export to backend
echo "Copying static files to backend..."
cp -r out ../backend/static

echo "Build complete!"
