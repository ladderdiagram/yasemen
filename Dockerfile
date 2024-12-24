FROM python:3.9-slim

# Install FFmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create uploads directory with permissions
RUN mkdir -p uploads && chmod 777 uploads

# Environment variables
ENV PORT=10000

# Run the application with increased timeout
CMD gunicorn --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 4 \
    --timeout 300 \
    --keep-alive 5 \
    --log-level debug \
    --worker-class sync \
    app:app
