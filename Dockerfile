FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY whale_watchtower/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY whale_watchtower/ ./whale_watchtower/

# Run the watcher
CMD ["python", "-u", "whale_watchtower/watcher.py"]
