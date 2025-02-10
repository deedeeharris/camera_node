#!/bin/bash

# Script to completely remove camera_node

# Stop and disable the service
echo "Stopping and disabling camera_node service..."
sudo systemctl stop camera_node.service || true
sudo systemctl disable camera_node.service || true

# Remove the systemd service file
echo "Removing systemd service file..."
sudo rm -f /etc/systemd/system/camera_node.service

# Remove the project directory
echo "Removing project directory..."
sudo rm -rf /home/user/camera_node  # Double-check this path!

# Reload systemd to ensure changes are applied
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Clear any failed service states
echo "Resetting failed service states..."
sudo systemctl reset-failed

echo "camera_node has been removed."