#!/bin/bash
# =============================================================================
# Automated deployment script for Zana Web App
# Deploys to GCP VM with domain zana-ai.com
#
# Usage: bash scripts/deploy_webapp.sh [domain] [email] [backend_port]
# Example: bash scripts/deploy_webapp.sh zana-ai.com your@email.com 8080
# =============================================================================

set -e  # Exit on error

DOMAIN="${1:-zana-ai.com}"
EMAIL="${2:-}"
BACKEND_PORT="${3:-8080}"
PROJECT_DIR="/opt/zana-bot/zana_planner"

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
else
    SUDO="sudo"
fi

# Step 1: Verify DNS
echo "[1/8] Verifying DNS configuration..."
DNS_IP=$(dig +short $DOMAIN | head -n 1 || echo "")
CURRENT_IP=$(curl -s ifconfig.me || echo "")

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
    echo "Please clone/pull the repository first."
    exit 1
fi

cd "$PROJECT_DIR"
echo "✓ Project directory: $(pwd)"

# Step 3: Pull latest code (if git repo)
echo ""
echo "[3/8] Updating code..."
if [ -d ".git" ]; then
    echo "Pulling latest changes from git..."
    git pull || echo "⚠️  Git pull failed, continuing with current code"
else
    echo "Not a git repository, skipping pull"
fi

# Step 4: Build frontend
echo ""
echo "[4/8] Building React frontend..."
if [ -d "webapp_frontend" ]; then
    cd webapp_frontend
    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm install
    fi
    echo "Building frontend..."
    npm run build
    cd ..
    echo "✓ Frontend built successfully"
else
    echo "⚠️  webapp_frontend directory not found, skipping frontend build"
fi

# Step 5: Build Docker image
echo ""
echo "[5/8] Building Docker image..."
docker compose build zana-prod
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
$SUDO tee /etc/nginx/sites-available/zana-ai > /dev/null <<EOF
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
$SUDO ln -sf /etc/nginx/sites-available/zana-ai /etc/nginx/sites-enabled/
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
docker compose up -d zana-prod

# Wait a moment for container to start
sleep 3

# Check container status
if docker compose ps zana-prod | grep -q "Up"; then
    echo "✓ Container is running"
else
    echo "⚠️  Container may not be running properly"
    echo "   Check logs: docker compose logs zana-prod"
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

echo "Testing public users endpoint..."
if curl -f -s "http://localhost:$BACKEND_PORT/api/public/users?limit=1" > /dev/null; then
    echo "✓ Public users endpoint working"
else
    echo "⚠️  Public users endpoint failed"
fi

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
echo "  curl https://$DOMAIN/api/public/users?limit=10"
echo ""
echo "Next steps:"
echo "  1. Configure BotFather menu button: https://$DOMAIN/"
echo "  2. View logs: docker compose logs -f zana-prod"
echo "  3. Check nginx logs: sudo tail -f /var/log/nginx/error.log"
echo ""

