FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg for audio processing and curl for healthcheck)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directories
RUN mkdir -p temp_resources/transcriptions

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Expose port
EXPOSE 80

# Command to run the application
CMD ["python", "app.py"] 