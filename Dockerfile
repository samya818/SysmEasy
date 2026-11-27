FROM python:3.11-slim

# Install Node.js for ELK (elkjs) layout engine
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications first for Docker layer caching
COPY requirements.txt pyproject.toml /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Install local ELK layout engine
RUN npm install --prefix elk_layout --no-audit --no-fund

EXPOSE 7860 8000

ENV PORT=7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
