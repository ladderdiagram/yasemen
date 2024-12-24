FROM python:3.9

# System dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    ncurses-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Environment variables
ENV PORT=10000

# Command to run the application
CMD gunicorn app:app --bind 0.0.0.0:$PORT
