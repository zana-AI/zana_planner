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

# Build arguments for version info
ARG GIT_COMMIT="unknown"
ARG GIT_TAG=""
ARG BUILD_DATE=""
ENV BOT_VERSION=${GIT_TAG:-${GIT_COMMIT}}
ENV BUILD_DATE=${BUILD_DATE}

# Create non-root user and directory structure
RUN useradd -m -u 1002 amiryan_j && \
    mkdir -p /app/USERS_DATA_DIR && \
    chown -R amiryan_j:amiryan_j /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/amiryan_j/.local

# Set working directory
WORKDIR /app

# Create VERSION file and ensure it's readable by the user
RUN echo "${GIT_TAG:-${GIT_COMMIT}}" > /app/VERSION && \
    chown amiryan_j:amiryan_j /app/VERSION && \
    chmod 644 /app/VERSION

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
