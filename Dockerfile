# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables to prevent bytecode and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install build dependencies and tools needed for downloading and extracting dezoomify
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Download and install dezoomify from the provided tarball URL
RUN wget https://github.com/lovasoa/dezoomify-rs/releases/download/v2.13.0/dezoomify-rs-linux.tgz && \
    tar -xzf dezoomify-rs-linux.tgz && \
    rm dezoomify-rs-linux.tgz && \
    chmod +x dezoomify-rs && \
    mv dezoomify-rs /usr/local/bin/dezoomify-rs

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port your app will run on
EXPOSE 5000

# Run the application using gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
