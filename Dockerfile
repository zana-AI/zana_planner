# Multi-stage build for Zana AI bot
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Create non-root user (matching host user UID for volume permissions)
RUN useradd -m -u 1002 amiryan_j && \
    mkdir -p /app/USERS_DATA_DIR /app/USERS_DATA_DIR_BACKUP && \
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
