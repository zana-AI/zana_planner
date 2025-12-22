#!/bin/bash
# =============================================================================
# Setup script for Zana AI Web App with nginx and SSL
# Run this on your server: bash setup_webapp_nginx.sh <domain> <email> [port]
# Example: bash setup_webapp_nginx.sh zanaai.duckdns.org you@email.com 8081
# =============================================================================

set -e

DOMAIN="${1:-zanaai.duckdns.org}"
EMAIL="${2:-}"
PORT="${3:-8081}"

if [ -z "$EMAIL" ]; then
    echo "Usage: $0 <domain> <email> [port]"
    echo "Example: $0 zanaai.duckdns.org you@email.com 8081"
    exit 1
fi

echo "========================================"
echo "Setting up nginx + SSL for Zana Web App"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Backend port: $PORT"
echo "========================================"

# Install nginx and certbot
echo "[1/5] Installing nginx and certbot..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Create nginx config
echo "[2/5] Creating nginx configuration..."
sudo tee /etc/nginx/sites-available/zanaai > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:$PORT;
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

# Enable the site
echo "[3/5] Enabling nginx site..."
sudo ln -sf /etc/nginx/sites-available/zanaai /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl reload nginx

# Open firewall ports
echo "[4/5] Configuring firewall..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 80/tcp || true
    sudo ufw allow 443/tcp || true
    echo "UFW rules added"
else
    echo "UFW not found, skipping firewall config"
    echo "Make sure ports 80 and 443 are open in your cloud provider's firewall"
fi

# Get SSL certificate
echo "[5/5] Obtaining SSL certificate..."
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect

echo ""
echo "========================================"
echo "✅ Setup complete!"
echo "========================================"
echo ""
echo "Your web app should now be accessible at:"
echo "  https://$DOMAIN/"
echo ""
echo "Test the API health endpoint:"
echo "  curl https://$DOMAIN/api/health"
echo ""
echo "Next step: Configure BotFather"
echo "  1. Open @BotFather in Telegram"
echo "  2. /mybots → Select your bot"
echo "  3. Bot Settings → Menu Button → Configure menu button"
echo "  4. URL: https://$DOMAIN/"
echo "  5. Button text: 📊 Weekly Report"
echo ""
