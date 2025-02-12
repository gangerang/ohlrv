# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables to prevent .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code.
COPY . .

EXPOSE 5000

# Run the application using gunicorn with an increased timeout.
CMD ["gunicorn", "--timeout", "120", "-b", "0.0.0.0:5000", "app:app"]