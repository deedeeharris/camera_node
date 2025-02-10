#!/bin/bash

# Script to update the camera_node Python script from the Git repository

REPO_URL="https://github.com/deedeeharris/camera_node.git"
PROJECT_DIR="/home/pi/camera_node"  # Must match the directory used in the installation script
TEMP_DIR="/tmp/camera_node_update"

# Check if the project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
  echo "Error: Project directory $PROJECT_DIR does not exist."
  echo "Please run the installation script first."
  exit 1
fi

# Create a temporary directory
mkdir -p "$TEMP_DIR"

# Clone the repository into the temporary directory
git clone "$REPO_URL" "$TEMP_DIR"

# Check if cloning was successful
if [ $? -ne 0 ]; then
  echo "Error: Failed to clone the repository."
  rm -rf "$TEMP_DIR"  # Clean up the temporary directory
  exit 1
fi

# Copy the Python file from the temporary directory to the project directory
# Overwrite the existing file
cp "$TEMP_DIR/camera_node.py" "$PROJECT_DIR/camera_node.py"

# Check if copying was successful
if [ $? -ne 0 ]; then
  echo "Error: Failed to copy the updated Python file."
  rm -rf "$TEMP_DIR"
  exit 1
fi

# Clean up the temporary directory
rm -rf "$TEMP_DIR"

# Restart the camera_node service
echo "Restarting camera_node service..."
sudo systemctl restart camera_node.service

if [ $? -ne 0 ]; then
  echo "Error: Failed to restart the camera_node service."
  exit 1
fi

echo "Camera node Python script updated successfully."
echo "The service has been restarted."

exit 0