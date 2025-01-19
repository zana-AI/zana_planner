#!/bin/bash

# Update package list and install Python and pip
echo "Updating package list..."
sudo apt-get update

echo "Installing Python and pip..."
sudo apt-get install -y python3 python3-pip

# Create a virtual environment in the root folder of the repo
echo "Creating a virtual environment..."
python3 -m venv .venv

# Activate the virtual environment
echo "Activating the virtual environment..."
source .venv/bin/activate

# Install required Python packages
echo "Installing required Python packages from requirements.txt..."
pip install -r requirements.txt

echo "Installation complete!"