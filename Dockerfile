# ==========================================
# STAGE 1: The Builder
# ==========================================
FROM python:3.10-slim AS builder

WORKDIR /build

# Copy only requirements to leverage Docker caching
COPY requirements.txt .

# Install dependencies into a specific folder (/install) instead of globally
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


# ==========================================
# STAGE 2: The Runner (The Final Image)
# ==========================================
FROM python:3.10-slim

WORKDIR /app

# Set Python environment variables (No .pyc files, no buffering)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# COPY ONLY THE FINISHED DEPENDENCIES FROM STAGE 1
COPY --from=builder /install /usr/local

# Copy your actual application code (app.py, templates, static)
COPY . /app/

# Expose the port
EXPOSE 8000

# Run the application
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8000", "app:app"]