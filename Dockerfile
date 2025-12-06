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

# Create non-root user
RUN useradd -m -u 1000 zana && \
    mkdir -p /app/users_data && \
    chown -R zana:zana /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/zana/.local

# Set working directory
WORKDIR /app

# Copy application code
COPY tm_bot/ ./tm_bot/
COPY bot_stats.py ./

# Make sure local bin is in PATH
ENV PATH=/home/zana/.local/bin:$PATH
ENV PYTHONPATH=/app

# Switch to non-root user
USER zana

# Set entrypoint
ENTRYPOINT ["python", "-m", "tm_bot.planner_bot"]
