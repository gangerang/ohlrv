#!/bin/bash

# Set the container name, image name, and port
CONTAINER_NAME="ohlrv"
IMAGE_NAME="ohlrv"
PORT="5000" # Change this to your desired port

echo "Stopping and removing existing container..."
docker stop $CONTAINER_NAME
docker rm $CONTAINER_NAME

echo "Removing existing image..."
docker rmi $IMAGE_NAME

echo "Building new image..."
docker build -t $IMAGE_NAME .

echo "Starting new container with port mapping..."
docker run -d -p $PORT:$PORT --name $CONTAINER_NAME $IMAGE_NAME

echo "Deployment complete! Container is running on port $PORT"