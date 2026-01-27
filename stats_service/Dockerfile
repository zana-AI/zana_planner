# Stats service Dockerfile
FROM python:3.11-slim

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (matching host user UID for volume permissions)
RUN useradd -m -u 1002 amiryan_j && \
    mkdir -p /app/USERS_DATA_DIR && \
    chown -R amiryan_j:amiryan_j /app

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi==0.104.1 uvicorn[standard]==0.24.0 logtail-python

# Copy stats service code
COPY stats_service/stats_service.py ./stats_service.py
COPY tm_bot/ ./tm_bot/

# Make sure Python can find modules
ENV PYTHONPATH=/app

# Switch to non-root user
USER amiryan_j

# Expose port
EXPOSE 8000

# Run stats service
CMD ["python", "-m", "uvicorn", "stats_service:app", "--host", "0.0.0.0", "--port", "8000"]
