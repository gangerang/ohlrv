#!/bin/bash

# Set the container name and image name
CONTAINER_NAME="ohlrv_container"
IMAGE_NAME="ohlrv_image"

echo "Stopping and removing existing container..."
docker stop $CONTAINER_NAME
docker rm $CONTAINER_NAME

echo "Removing existing image..."
docker rmi $IMAGE_NAME

echo "Building new image..."
docker build -t $IMAGE_NAME .

echo "Starting new container..."
docker run -d --name $CONTAINER_NAME $IMAGE_NAME

echo "Deployment complete!"
