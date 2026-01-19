#!/bin/bash
# =============================================================================
# DEPRECATED: Use GitHub Actions for deployments
# 
# This script is kept for backward compatibility but should not be used
# for regular deployments. Use GitHub Actions workflows instead:
# - Staging: auto-deploys on push to master
# - Production: manual promotion from staging
#
# For one-time infrastructure setup, use: scripts/setup_infrastructure.sh
#
# Usage: bash scripts/deploy_webapp.sh [domain] [email] [backend_port]
# =============================================================================

set -e  # Exit on error

DOMAIN="${1:-xaana.club}"
EMAIL="${2:-}"
BACKEND_PORT="${3:-8080}"

# Auto-detect project directory
# Try common locations
if [ -d "/opt/zana-bot/zana_planner" ]; then
    PROJECT_DIR="/opt/zana-bot/zana_planner"
elif [ -d "/opt/zana-bot" ] && [ -f "/opt/zana-bot/docker-compose.yml" ]; then
    PROJECT_DIR="/opt/zana-bot"
elif [ -d "$(pwd)/zana_planner" ] && [ -f "$(pwd)/zana_planner/docker-compose.yml" ]; then
    PROJECT_DIR="$(pwd)/zana_planner"
elif [ -f "$(pwd)/docker-compose.yml" ]; then
    PROJECT_DIR="$(pwd)"
else
    PROJECT_DIR="/opt/zana-bot/zana_planner"  # Default fallback
fi

echo "========================================"
echo "Zana Web App - Automated Deployment"
echo "========================================"
echo "Domain: $DOMAIN"
echo "Backend port: $BACKEND_PORT"
echo "Project dir: $PROJECT_DIR"
echo ""

# Check if running as root for nginx/certbot operations
if [ "$EUID" -eq 0 ]; then
    SUDO=""
    DOCKER_CMD="docker"
    DOCKER_COMPOSE_CMD="docker compose"
else
    SUDO="sudo"
    # Check if user can run docker without sudo
    if docker info &>/dev/null; then
        DOCKER_CMD="docker"
        DOCKER_COMPOSE_CMD="docker compose"
    else
        DOCKER_CMD="sudo docker"
        DOCKER_COMPOSE_CMD="sudo docker compose"
    fi
fi

# Step 1: Verify DNS
echo "[1/8] Verifying DNS configuration..."
# Try multiple DNS lookup methods
if command -v dig &> /dev/null; then
    DNS_IP=$(dig +short $DOMAIN | head -n 1 || echo "")
elif command -v host &> /dev/null; then
    DNS_IP=$(host -t A $DOMAIN | grep -oP 'has address \K[0-9.]+' | head -n 1 || echo "")
elif command -v nslookup &> /dev/null; then
    DNS_IP=$(nslookup $DOMAIN | grep -A 1 "Name:" | grep "Address:" | awk '{print $2}' | head -n 1 || echo "")
else
    DNS_IP=""
fi

CURRENT_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ifconfig.co 2>/dev/null || echo "")

if [ -z "$DNS_IP" ]; then
    echo "⚠️  WARNING: Could not resolve $DOMAIN. DNS may not be configured yet."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ DNS resolved: $DOMAIN → $DNS_IP"
    if [ "$DNS_IP" != "$CURRENT_IP" ] && [ -n "$CURRENT_IP" ]; then
        echo "⚠️  WARNING: DNS IP ($DNS_IP) doesn't match current server IP ($CURRENT_IP)"
    fi
fi

# Step 2: Navigate to project directory
echo ""
echo "[2/8] Checking project directory..."
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Error: Project directory not found: $PROJECT_DIR"
    echo ""
    echo "Trying to auto-detect from current location..."
    CURRENT_DIR=$(pwd)
    if [ -f "$CURRENT_DIR/docker-compose.yml" ]; then
        PROJECT_DIR="$CURRENT_DIR"
        echo "✓ Found project at: $PROJECT_DIR"
    else
        echo "Please run this script from the project root directory (where docker-compose.yml is located)"
        echo "Or specify the correct path by editing PROJECT_DIR in the script"
        exit 1
    fi
fi

cd "$PROJECT_DIR"
echo "✓ Project directory: $(pwd)"

# Verify we're in the right place
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found in $PROJECT_DIR"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Step 3: Pull latest code (if git repo)
echo ""
echo "[3/8] Updating code..."
if [ -d ".git" ]; then
    echo "Pulling latest changes from git..."
    # Try to fix git permissions if needed
    if ! git pull 2>&1 | grep -q "Permission denied"; then
        echo "✓ Code updated"
    else
        echo "⚠️  Git pull failed (permission issue), trying with sudo..."
        $SUDO git pull || echo "⚠️  Git pull failed, continuing with current code"
    fi
else
    echo "Not a git repository, skipping pull"
fi

# Step 4: Build frontend (optional - Docker will build it if npm not available)
echo ""
echo "[4/8] Building React frontend..."
# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "⚠️  npm not found on host system"
    echo "   Frontend will be built inside Docker during image build (this is fine)"
    echo "   To build locally, install Node.js: sudo apt-get install -y nodejs npm"
else
    # Check for webapp_frontend in current dir or zana_planner subdir
    FRONTEND_DIR=""
    if [ -d "webapp_frontend" ]; then
        FRONTEND_DIR="webapp_frontend"
    elif [ -d "zana_planner/webapp_frontend" ]; then
        FRONTEND_DIR="zana_planner/webapp_frontend"
    fi

    if [ -n "$FRONTEND_DIR" ]; then
        cd "$FRONTEND_DIR"
        if [ ! -d "node_modules" ]; then
            echo "Installing npm dependencies..."
            npm install
        fi
        echo "Building frontend..."
        npm run build
        cd "$PROJECT_DIR"
        echo "✓ Frontend built successfully"
    else
        echo "⚠️  webapp_frontend directory not found, skipping frontend build"
        echo "   (Frontend will be built in Docker)"
    fi
fi

# Step 5: Build Docker image
echo ""
echo "[5/8] Building Docker image..."
$DOCKER_COMPOSE_CMD build zana-prod
echo "✓ Docker image built"

# Step 6: Install/configure nginx
echo ""
echo "[6/8] Configuring nginx..."

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx and certbot..."
    $SUDO apt-get update
    $SUDO apt-get install -y nginx certbot python3-certbot-nginx
fi

# Create nginx configuration
echo "Creating nginx configuration..."
$SUDO tee /etc/nginx/sites-available/xaana > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }
}
EOF

# Enable site
$SUDO ln -sf /etc/nginx/sites-available/xaana /etc/nginx/sites-enabled/
$SUDO rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test nginx config
if $SUDO nginx -t; then
    echo "✓ Nginx configuration valid"
    $SUDO systemctl reload nginx
    echo "✓ Nginx reloaded"
else
    echo "❌ Nginx configuration test failed!"
    exit 1
fi

# Step 7: Configure firewall
echo ""
echo "[7/8] Configuring firewall..."

# Check if gcloud is available
if command -v gcloud &> /dev/null; then
    echo "Configuring GCP firewall rules..."
    
    # Check if rules exist
    if ! gcloud compute firewall-rules describe allow-http &> /dev/null; then
        gcloud compute firewall-rules create allow-http \
            --allow tcp:80 \
            --source-ranges 0.0.0.0/0 \
            --description "Allow HTTP traffic" \
            --quiet || echo "⚠️  Failed to create HTTP firewall rule"
    fi
    
    if ! gcloud compute firewall-rules describe allow-https &> /dev/null; then
        gcloud compute firewall-rules create allow-https \
            --allow tcp:443 \
            --source-ranges 0.0.0.0/0 \
            --description "Allow HTTPS traffic" \
            --quiet || echo "⚠️  Failed to create HTTPS firewall rule"
    fi
    echo "✓ GCP firewall rules configured"
else
    echo "⚠️  gcloud CLI not found, skipping GCP firewall configuration"
    echo "   Please configure firewall rules manually in GCP Console"
fi

# Configure local firewall (UFW)
if command -v ufw &> /dev/null; then
    $SUDO ufw allow 80/tcp 2>/dev/null || true
    $SUDO ufw allow 443/tcp 2>/dev/null || true
    echo "✓ Local firewall (UFW) configured"
fi

# Step 8: Get SSL certificate (if email provided)
if [ -n "$EMAIL" ]; then
    echo ""
    echo "[8/8] Setting up SSL certificate..."
    
    # Check if certificate already exists
    if $SUDO certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
        echo "✓ SSL certificate already exists for $DOMAIN"
        echo "Testing renewal..."
        $SUDO certbot renew --dry-run || echo "⚠️  Certificate renewal test failed"
    else
        echo "Obtaining SSL certificate from Let's Encrypt..."
        $SUDO certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
            --non-interactive --agree-tos \
            -m "$EMAIL" \
            --redirect || {
            echo "⚠️  Failed to obtain SSL certificate"
            echo "   This might be because:"
            echo "   - DNS hasn't fully propagated"
            echo "   - Port 80 is not accessible"
            echo "   - Domain is already in use"
            echo "   You can run this script again later to retry"
        }
    fi
else
    echo ""
    echo "[8/8] Skipping SSL setup (no email provided)"
    echo "   To set up SSL later, run:"
    echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -m your@email.com"
fi

# Step 9: Start/restart Docker container
echo ""
echo "[9/9] Starting Docker container..."
$DOCKER_COMPOSE_CMD up -d zana-prod

# Wait a moment for container to start
sleep 3

# Check container status
if $DOCKER_COMPOSE_CMD ps zana-prod | grep -q "Up"; then
    echo "✓ Container is running"
else
    echo "⚠️  Container may not be running properly"
    echo "   Check logs: $DOCKER_COMPOSE_CMD logs zana-prod"
fi

# Step 10: Verify deployment
echo ""
echo "[10/10] Verifying deployment..."

# Wait a bit for services to be ready
sleep 2

# Test endpoints
echo "Testing health endpoint..."
if curl -f -s "http://localhost:$BACKEND_PORT/api/health" > /dev/null; then
    echo "✓ Backend health check passed"
else
    echo "⚠️  Backend health check failed"
fi

echo "Skipping public users endpoint (auth required)"

# Test through nginx (if SSL is set up)
if $SUDO certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
    echo "Testing HTTPS endpoint..."
    if curl -f -s "https://$DOMAIN/api/health" > /dev/null; then
        echo "✓ HTTPS endpoint working"
    else
        echo "⚠️  HTTPS endpoint failed (may need DNS propagation)"
    fi
fi

echo ""
echo "========================================"
echo "✅ Deployment complete!"
echo "========================================"
echo ""
echo "⚠️  WARNING: This script rebuilds containers manually."
echo "   For regular deployments, use GitHub Actions workflows:"
echo "   - Staging: auto-deploys on push to master"
echo "   - Production: manual promotion from staging"
echo ""
echo "Your web app should be accessible at:"
if $SUDO certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
    echo "  https://$DOMAIN/"
    echo "  https://www.$DOMAIN/"
else
    echo "  http://$DOMAIN/ (HTTP only - set up SSL with email parameter)"
fi
echo ""
echo "Test endpoints:"
echo "  curl https://$DOMAIN/api/health"
echo "  (public users endpoint requires auth)"
echo ""
echo "Next steps:"
echo "  1. Configure BotFather menu button: https://$DOMAIN/"
echo "  2. View logs: $DOCKER_COMPOSE_CMD logs -f zana-prod"
echo "  3. Check nginx logs: sudo tail -f /var/log/nginx/error.log"
echo ""
echo "For future deployments, rely on GitHub Actions instead of this script."
echo ""

