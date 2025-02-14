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
    curl \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Compile and install dezoomify from the Git repository
RUN cargo install --git https://github.com/jnflint/dezoomify-jf/releases/tag/v2.13.1beta

RUN chmod +x dezoomify-rs

RUN mv dezoomify-rs /usr/local/bin/dezoomify-rs

# Copy Python dependencies and install them
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]