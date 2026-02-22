FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install procps for HEALTHCHECK
RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY *.py ./

# Build arguments and environment variables
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Create data directory for SQLite DB
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/morgen_bot.db

# Healthcheck to verify the bot process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ps -ef | grep "[p]ython bot.py" || exit 1

# Run the application
CMD ["python", "bot.py"]
