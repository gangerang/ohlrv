# Use Debian Buster slim as base image
FROM debian:buster-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Make python3 the default python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Download and install dezoomify-rs from the provided tarball URL
RUN wget https://github.com/lovasoa/dezoomify-rs/releases/download/v2.7.2/dezoomify-rs-linux.tgz && \
    tar -xzf dezoomify-rs-linux.tgz && \
    rm dezoomify-rs-linux.tgz && \
    chmod +x dezoomify-rs && \
    mv dezoomify-rs /usr/local/bin/dezoomify-rs

# Copy Python dependencies and install them
COPY requirements.txt .
RUN pip3 install --upgrade pip && pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]