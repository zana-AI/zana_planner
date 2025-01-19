#!/bin/bash

# Update package list and install Python and pip
echo "Updating package list..."
sudo apt-get update

echo "Installing Python and pip..."
sudo apt-get install -y python3 python3-pip python3-venv
sudo apt install python3.11-venv

# Check if the .env file exists, if not create an empty one with placeholders
if [ ! -f ".env" ]; then
    echo "Creating an empty .env file with placeholders..."
    echo "BOT_TOKEN=\"your_bot_token_here\"" > .env
    echo "OPENAI_API_KEY=\"your_openai_api_key_here\"" >> .env
    echo "ROOT_DIR=\"your_root_directory_here\"" >> .env
else
    echo ".env file already exists. Skipping creation."
fi

# Check if the USERS_DATA_DIR directory exists, if not create it
if [ ! -d "USERS_DATA_DIR" ]; then
    echo "Creating USERS_DATA_DIR directory..."
    mkdir USERS_DATA_DIR
else
    echo "USERS_DATA_DIR directory already exists. Skipping creation."
fi

# Check if the virtual environment already exists
if [ ! -d ".venv" ]; then
    # Create a virtual environment in the root folder of the repo
    echo "Creating a virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists. Skipping creation."
fi

# Activate the virtual environment
echo "Activating the virtual environment..."
source .venv/bin/activate

# Install required Python packages
echo "Installing required Python packages from requirements.txt..."
pip install --break-system-packages -r requirements.txt

echo "Installation complete!"