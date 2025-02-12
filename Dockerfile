# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies needed for building and downloading
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Download and install dezoomify-rs from the provided tarball URL
RUN wget https://github.com/lovasoa/dezoomify-rs/releases/download/v2.13.0/dezoomify-rs-linux.tgz && \
    tar -xzf dezoomify-rs-linux.tgz && \
    rm dezoomify-rs-linux.tgz && \
    chmod +x dezoomify-rs && \
    mv dezoomify-rs /usr/local/bin/dezoomify-rs

# Copy Python dependencies and install them
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]