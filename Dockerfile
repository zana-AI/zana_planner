# syntax=docker/dockerfile:1.4
# Multi-stage build for Zana AI bot

# =============================================================================
# Stage 1: Build React frontend
# =============================================================================
FROM node:20-slim as frontend-builder

WORKDIR /app/webapp_frontend

# Copy package files first for better layer caching
COPY webapp_frontend/package.json webapp_frontend/package-lock.json* ./

# Install dependencies
RUN npm install --frozen-lockfile || npm install

# Copy frontend source
COPY webapp_frontend/ ./

# Build the React app
RUN npm run build

# =============================================================================
# Stage 2: Build Python dependencies
# =============================================================================
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Use BuildKit cache mount for pip cache to speed up rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Build arguments for version info
ARG GIT_COMMIT="unknown"
ARG GIT_TAG=""
ARG BUILD_DATE=""
ARG GIT_COMMIT_MESSAGE=""
ARG GIT_COMMIT_AUTHOR=""
ARG GIT_COMMIT_DATE=""
ENV BOT_VERSION=${GIT_TAG:-${GIT_COMMIT}}
ENV BUILD_DATE=${BUILD_DATE}

# Create non-root user and directory structure
RUN useradd -m -u 1002 amiryan_j && \
    mkdir -p /app/USERS_DATA_DIR && \
    chown -R amiryan_j:amiryan_j /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/amiryan_j/.local

# ----------------------------------------------------------------------------
# Playwright (Chromium) + fonts for high-quality RTL rendering
# ----------------------------------------------------------------------------
# Store browser binaries in a shared, non-home path.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# System fonts (broad Unicode coverage) + Playwright's runtime deps for Chromium.
# - We install Noto fonts explicitly for consistent rendering across languages.
# - We install Playwright Chromium dependencies via `install-deps` as root.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright OS dependencies for Chromium (uses apt internally).
# The python packages live in /home/amiryan_j/.local (copied from builder), so we add that to PYTHONPATH.
RUN PYTHONPATH=/home/amiryan_j/.local/lib/python3.11/site-packages \
    python -m playwright install-deps chromium

# Create a shared browser cache directory and grant runtime user access.
RUN mkdir -p /ms-playwright && chown -R amiryan_j:amiryan_j /ms-playwright

# Set working directory
WORKDIR /app

# Create VERSION file and ensure it's readable by the user
RUN echo "${GIT_TAG:-${GIT_COMMIT}}" > /app/VERSION && \
    chown amiryan_j:amiryan_j /app/VERSION && \
    chmod 644 /app/VERSION

# Create COMMIT_INFO.json file with commit metadata
# Write Python script to handle JSON escaping properly
RUN printf 'import json\n\
import sys\n\
commit = sys.argv[1] if len(sys.argv) > 1 else "unknown"\n\
message = sys.argv[2] if len(sys.argv) > 2 else ""\n\
author = sys.argv[3] if len(sys.argv) > 3 else ""\n\
date = sys.argv[4] if len(sys.argv) > 4 else ""\n\
commit_info = {"commit": commit, "message": message, "author": author, "date": date}\n\
with open("/app/COMMIT_INFO.json", "w") as f:\n\
    json.dump(commit_info, f)\n\
' > /tmp/create_commit_info.py && \
    python3 /tmp/create_commit_info.py "${GIT_COMMIT}" "${GIT_COMMIT_MESSAGE}" "${GIT_COMMIT_AUTHOR}" "${GIT_COMMIT_DATE}" && \
    rm /tmp/create_commit_info.py && \
    chown amiryan_j:amiryan_j /app/COMMIT_INFO.json && \
    chmod 644 /app/COMMIT_INFO.json

# Copy application code
COPY tm_bot/ ./tm_bot/
COPY bot_stats.py ./
COPY scripts/ ./scripts/

# Copy built frontend from frontend-builder stage
COPY --from=frontend-builder /app/webapp_frontend/dist ./webapp_frontend/dist

# Make sure local bin is in PATH
ENV PATH=/home/amiryan_j/.local/bin:$PATH
ENV PYTHONPATH=/app:/app/tm_bot

# Expose web app port
EXPOSE 8080

# Switch to non-root user
USER amiryan_j

# Download Chromium browser binaries to PLAYWRIGHT_BROWSERS_PATH.
RUN python -m playwright install chromium

# Set entrypoint
ENTRYPOINT ["python", "-m", "tm_bot.run_bot"]
