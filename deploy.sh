#!/bin/bash
# ============================================================
# Whale Watchtower - Cloud Deployment Script
# Run this on a fresh Ubuntu server (Oracle Cloud, AWS, etc.)
# ============================================================

set -e

echo "=========================================="
echo "  Whale Watchtower - Server Setup"
echo "=========================================="

# Update system
echo "[1/5] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Docker
echo "[2/5] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to log out and back in for group changes."
else
    echo "Docker already installed."
fi

# Install Docker Compose
echo "[3/5] Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    sudo apt install -y docker-compose-plugin
else
    echo "Docker Compose already installed."
fi

# Clone repo
echo "[4/5] Cloning repository..."
if [ ! -d "crypto_moves" ]; then
    git clone https://github.com/nazargeldy/crypto_moves.git
    cd crypto_moves
else
    cd crypto_moves
    git pull origin main
fi

# Check for config
echo "[5/5] Checking configuration..."
if [ ! -f "whale_watchtower/config.json" ]; then
    echo ""
    echo "!! config.json not found !!"
    echo "Copy config.example.json and fill in your credentials:"
    echo "  cp whale_watchtower/config.example.json whale_watchtower/config.json"
    echo "  nano whale_watchtower/config.json"
    echo ""
    echo "Then start the watchtower with:"
    echo "  docker compose up -d --build"
    exit 1
fi

# Build and start
echo ""
echo "Starting Whale Watchtower..."
docker compose up -d --build

echo ""
echo "=========================================="
echo "  Watchtower is LIVE!"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  docker compose logs -f          # View live logs"
echo "  docker compose restart           # Restart"
echo "  docker compose down              # Stop"
echo "  docker compose up -d --build     # Rebuild & restart"
echo ""
