# Use an Ubuntu 20.04 base image
FROM ubuntu:20.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.9, pip, and necessary build dependencies
RUN apt-get update && apt-get install -y \
    python3.9 python3.9-distutils python3-pip \
    gcc wget tar curl build-essential pkg-config libssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# (Optional) Ensure "python" points to python3.9
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.9 1

# Install Rust toolchain using rustup
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Build and install dezoomify from the Git repository.
# Note: Adjust the repository URL and tag as necessary. Here we use the version known to work.
RUN cargo install --git https://github.com/jnflint/dezoomify-jf.git --tag v2.13.1beta

# Move the built binary to a system-wide location
RUN mv /root/.cargo/bin/dezoomify-rs /usr/local/bin/dezoomify-rs && chmod +x /usr/local/bin/dezoomify-rs

# Set the working directory
WORKDIR /app

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip3 install --upgrade pip && pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 5000 for the Flask app
EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]
