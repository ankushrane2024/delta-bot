# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user
RUN groupadd -r ares && useradd -r -g ares ares

# Set working directory
WORKDIR /app

# Install dependencies (assuming requirements.txt exists)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt || echo "No requirements.txt found, skipping..."

# Copy the application code
COPY . /app/

# Ensure proper permissions for the non-root user
RUN mkdir -p /app/logs /app/data && chown -R ares:ares /app

# Switch to non-root user
USER ares

# Expose the dashboard API port
EXPOSE 8000

# Healthcheck to verify the FastAPI health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ./healthcheck.sh || exit 1

# Start the application using the entrypoint script
CMD ["./startup.sh"]
