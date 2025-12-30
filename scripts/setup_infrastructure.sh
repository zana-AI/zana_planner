#!/bin/bash
# =============================================================================
# One-time infrastructure setup for Zana Web App
# Sets up nginx, SSL certificate, and firewall rules
# Run this ONCE after initial deployment
#
# Usage: bash scripts/setup_infrastructure.sh [domain] [email]
# Example: bash scripts/setup_infrastructure.sh zana-ai.com your@email.com
# =============================================================================

set -e

DOMAIN="${1:-zana-ai.com}"
EMAIL="${2:-}"
BACKEND_PORT="${3:-8080}"

echo "========================================"
echo "Zana Web App - Infrastructure Setup"
echo "========================================"
echo "Domain: $DOMAIN"
echo "Backend port: $BACKEND_PORT"
echo ""
echo "This script sets up nginx, SSL, and firewall."
echo "Container deployment is handled by GitHub Actions."
echo ""

# Check if running as root for nginx/certbot operations
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Step 1: Verify DNS
echo "[1/5] Verifying DNS configuration..."
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

# Step 2: Install nginx and certbot
echo ""
echo "[2/5] Installing nginx and certbot..."
if ! command -v nginx &> /dev/null; then
    $SUDO apt-get update
    $SUDO apt-get install -y nginx certbot python3-certbot-nginx
    echo "✓ nginx and certbot installed"
else
    echo "✓ nginx already installed"
fi

# Step 3: Configure nginx
echo ""
echo "[3/5] Configuring nginx..."
# Create nginx configuration
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

# Step 4: Configure firewall
echo ""
echo "[4/5] Configuring firewall..."

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

# Step 5: Get SSL certificate
echo ""
echo "[5/5] Setting up SSL certificate..."
if [ -n "$EMAIL" ]; then
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
    echo "⚠️  No email provided, skipping SSL setup"
    echo "   To set up SSL later, run:"
    echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN -m your@email.com"
fi

echo ""
echo "========================================"
echo "✅ Infrastructure setup complete!"
echo "========================================"
echo ""
echo "Nginx is configured to proxy:"
echo "  https://$DOMAIN/ → http://localhost:$BACKEND_PORT/"
echo ""
echo "Next steps:"
echo "  1. Ensure your container is running (GitHub Actions will deploy it)"
echo "  2. Test: curl https://$DOMAIN/api/health"
echo "  3. Configure BotFather menu button: https://$DOMAIN/"
echo ""
echo "Note: Container deployments are handled by GitHub Actions workflows."
echo "      This script only sets up infrastructure (nginx, SSL, firewall)."
echo ""

