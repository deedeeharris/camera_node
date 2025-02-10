#!/bin/bash

# Script to install and run camera_node on Raspberry Pi

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Update and upgrade system
echo "Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

# Install git
if ! command_exists git; then
  echo "Installing git..."
  sudo apt-get install git -y
else
  echo "Git is already installed."
fi

# Check if a Node ID is provided as an argument
if [ -z "$1" ]; then
  echo "Error: Please provide a Node ID as an argument."
  echo "Usage: $0 <NODE_ID>"
  exit 1
fi

NODE_ID="$1"
REPO_URL="https://github.com/deedeeharris/camera_node.git"
PROJECT_DIR="/home/pi/camera_node"  # You can change this if you want a different directory

# Clone the repository
if [ -d "$PROJECT_DIR" ]; then
  echo "Project directory $PROJECT_DIR already exists.  Pulling latest changes..."
  cd "$PROJECT_DIR"
  git pull
else
  echo "Cloning repository..."
  git clone "$REPO_URL" "$PROJECT_DIR"
  cd "$PROJECT_DIR"
fi


# Install Python requirements
echo "Installing Python requirements..."
if command_exists pip; then
    pip install -r requirements.txt
elif command_exists pip3; then
    pip3 install -r requirements.txt
else
    echo "Error: Neither pip nor pip3 is installed. Please install pip."
    exit 1
fi

# Update .env file with the provided NODE_ID
echo "Updating .env file with NODE_ID=$NODE_ID..."
if [ -f "$PROJECT_DIR/.env.txt" ]; then
  sed -i "s/NODE_ID=.*/NODE_ID=$NODE_ID/" "$PROJECT_DIR/.env.txt"
else
  echo "NODE_ID=$NODE_ID" > "$PROJECT_DIR/.env.txt"
  echo "PORT=5001" >> "$PROJECT_DIR/.env.txt" # Add default port if .env.txt didn't exist
fi

# Create systemd service file
echo "Creating systemd service file..."
sudo tee /etc/systemd/system/camera_node.service > /dev/null <<EOF
[Unit]
Description=Camera Node Service
After=network.target

[Service]
User=pi
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/camera_node.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
echo "Enabling and starting camera_node service..."
sudo systemctl daemon-reload
sudo systemctl enable camera_node.service
sudo systemctl start camera_node.service

echo "Camera node installation and setup complete."
echo "The service is running in the background."
echo "You can check its status with: sudo systemctl status camera_node.service"
echo "You can view logs with: journalctl -u camera_node.service"

exit 0