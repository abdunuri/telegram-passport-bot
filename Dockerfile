FROM mcr.microsoft.com/playwright/python:v1.41.1-jammy

WORKDIR /app

# Install additional system dependencies that might be needed
RUN apt-get update && \
    apt-get install -y \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary files (better than copying everything)
COPY requirements.txt .
COPY ICS_passport.py .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and dependencies
RUN playwright install chromium
RUN playwright install-deps

# Clean up to reduce image size
RUN apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables for better Playwright performance
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/google-chrome-stable
ENV DISPLAY=:99

# Create a non-root user for security
RUN useradd -m botuser
USER botuser

# Health check (optional but recommended)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)"

CMD ["python", "ICS_passport.py"]