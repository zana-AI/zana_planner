# syntax=docker/dockerfile:1.4
# Multi-stage build for Zana AI bot
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

# Add this before copying code (after WORKDIR /app)
# Get git version info and save to VERSION file
ARG GIT_COMMIT="unknown"
ARG GIT_TAG=""
ARG BUILD_DATE=""
ENV BOT_VERSION=${GIT_TAG:-${GIT_COMMIT}}
ENV BUILD_DATE=${BUILD_DATE}

# Create VERSION file
RUN echo "${GIT_TAG:-${GIT_COMMIT}}" > /app/VERSION || echo "unknown" > /app/VERSION

# Create non-root user (matching host user UID for volume permissions)
RUN useradd -m -u 1002 amiryan_j && \
    mkdir -p /app/USERS_DATA_DIR /app/USERS_DATA_DIR && \
    chown -R amiryan_j:amiryan_j /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/amiryan_j/.local

# Set working directory
WORKDIR /app

# Copy application code
COPY tm_bot/ ./tm_bot/
COPY bot_stats.py ./

# Make sure local bin is in PATH
ENV PATH=/home/amiryan_j/.local/bin:$PATH
ENV PYTHONPATH=/app:/app/tm_bot

# Switch to non-root user
USER amiryan_j

# Set entrypoint
ENTRYPOINT ["python", "-m", "tm_bot.planner_bot"]
