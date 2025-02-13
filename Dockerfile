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
# local version used to use 2.6.5 but can't run here
# latest version 2.13.0 works but uses png so fails
# 2.9.4 is min version which works but still png (create releases from ubuntu 20.04 instead of 18.04)
# 2.9.3 doesn't work, still png
# 2.7.2 doesn't work but max version with jpg
# 2.6.5 doesn't work but uses jpg and was local version
RUN wget -O dezoomify-rs https://github.com/jnflint/dezoomify-jf/releases/download/v2.13.1beta/dezoomify-rs

RUN ls -a

RUN chmod +x dezoomify-rs

RUN ./dezoomify-rs --version

RUN mv dezoomify-rs /usr/local/bin/dezoomify-rs

# Copy Python dependencies and install them
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

EXPOSE 5000

# Run the application with gunicorn
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]