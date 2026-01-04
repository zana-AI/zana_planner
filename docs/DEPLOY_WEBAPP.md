# Deploy Zana Web App to GCP with Domain (xaana.club)

This guide walks you through deploying the Zana web app to your GCP VM with the domain `xaana.club`.

## 🚀 Quick Start: Automated Deployment

**Recommended:** Use the automated deployment script for a one-command setup:

```bash
# SSH into your VM
ssh your-username@34.163.204.33

# Run automated deployment (first time)
cd /opt/zana-bot/zana_planner
bash scripts/deploy_webapp.sh xaana.club your-email@example.com
```

This script automatically:
- ✅ Verifies DNS configuration
- ✅ Pulls latest code
- ✅ Builds React frontend
- ✅ Builds Docker image
- ✅ Configures nginx
- ✅ Sets up SSL certificate
- ✅ Configures firewall
- ✅ Starts services
- ✅ Verifies deployment

**For subsequent deployments** (code updates only):
```bash
bash scripts/deploy_webapp_quick.sh
```

See [`scripts/README_DEPLOY.md`](scripts/README_DEPLOY.md) for detailed documentation.

---

## Manual Deployment (Alternative)

If you prefer manual steps or need to troubleshoot, follow the sections below.

---

## Prerequisites

- GCP VM instance running at IP: `34.163.204.33`
- SSH access to the VM
- Domain `xaana.club` registered on Namecheap
- Docker and Docker Compose installed on the VM
- Your bot token ready

---

## Step 1: Configure DNS on Namecheap

1. **Log in to Namecheap** and go to your domain management
2. **Go to Advanced DNS** for `xaana.club`
3. **Add/Update A Record**:
   - **Type**: A Record
   - **Host**: `@` (or leave blank for root domain)
   - **Value**: `34.163.204.33`
   - **TTL**: Automatic (or 300 seconds)
4. **Add/Update A Record for www** (optional but recommended):
   - **Type**: A Record
   - **Host**: `www`
   - **Value**: `34.163.204.33`
   - **TTL**: Automatic

**Note**: DNS propagation can take 5 minutes to 48 hours, but usually happens within 1-2 hours.

**Verify DNS** (from your local machine):
```bash
# Check if DNS is pointing to your VM
nslookup xaana.club
# Should return: 34.163.204.33

# Or use dig
dig xaana.club +short
```

---

## Step 2: Deploy Code to GCP VM

### 2.1 SSH into VM

```bash
ssh your-username@34.163.204.33
```

### 2.2 Clone/Update Code

```bash
# If code is already there, pull updates
cd /opt/zana-bot/zana_planner
git pull origin main  # or your branch name

# If first time, clone:
# cd /opt
# sudo git clone YOUR_REPO_URL zana-bot
# cd zana-bot/zana_planner
```

### 2.3 Build Frontend (if not already built)

The Dockerfile should build it automatically, but you can verify:

```bash
cd /opt/zana-bot/zana_planner/webapp_frontend
npm install
npm run build
```

### 2.4 Rebuild Docker Image

```bash
cd /opt/zana-bot/zana_planner
docker compose build zana-prod
```

---

## Step 3: Enable Webapp Server in Docker

The webapp server is currently disabled in `planner_bot.py`. We need to enable it. You have two options:

### Option A: Enable in planner_bot.py (Recommended)

Uncomment the webapp server code in `tm_bot/planner_bot.py` and rebuild.

### Option B: Run Separate Webapp Container (Alternative)

Create a separate service in docker-compose.yml that runs only the webapp.

**For now, let's use Option A** - I'll create a patch file you can apply:

```bash
# On your VM, edit the file
cd /opt/zana-bot/zana_planner
sudo nano tm_bot/planner_bot.py
```

Uncomment lines 250-291 (the `_start_webapp_server` method) and line 302-303 (the call to start it).

Then rebuild:
```bash
docker compose build zana-prod
```

---

## Step 4: Set Up Nginx on Host (Not in Docker)

Nginx should run on the **host machine** (not in Docker) to handle SSL/HTTPS and proxy to the Docker container.

### 4.1 Install Nginx

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### 4.2 Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/zana-ai
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name xaana.club www.xaana.club;

    # Redirect HTTP to HTTPS (will be added by certbot)
    # For now, proxy to backend
    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }
}
```

### 4.3 Enable the Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/zana-ai /etc/nginx/sites-enabled/

# Remove default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### 4.4 Open Firewall Ports

```bash
# Check GCP firewall rules (from GCP Console or gcloud CLI)
# Make sure ports 80 and 443 are open

# Using gcloud CLI (if you have it):
gcloud compute firewall-rules create allow-http \
    --allow tcp:80 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow HTTP traffic"

gcloud compute firewall-rules create allow-https \
    --allow tcp:443 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow HTTPS traffic"

# Also check local firewall (UFW)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

---

## Step 5: Get SSL Certificate with Let's Encrypt

**Wait for DNS to propagate first!** Verify with:
```bash
nslookup xaana.club
```

Then get SSL certificate:

```bash
# Replace with your email
sudo certbot --nginx -d xaana.club -d www.xaana.club \
    --non-interactive --agree-tos \
    --email your-email@example.com \
    --redirect
```

This will:
- Automatically configure nginx for HTTPS
- Set up automatic redirect from HTTP to HTTPS
- Configure auto-renewal

**Test SSL**:
```bash
curl https://xaana.club/api/health
```

---

## Step 6: Start/Restart Docker Container

```bash
cd /opt/zana-bot/zana_planner

# Stop existing container
docker compose stop zana-prod

# Start with new build
docker compose up -d zana-prod

# Check logs
docker compose logs -f zana-prod
```

Look for: `Web app server started on http://0.0.0.0:8080`

---

## Step 7: Verify Deployment

### 7.1 Test API Endpoints

```bash
# Health check
curl https://xaana.club/api/health

# Public users endpoint
curl https://xaana.club/api/public/users?limit=10
```

### 7.2 Test in Browser

1. Open: `https://xaana.club`
2. Should show the public users page (or empty state if no users)
3. Open browser console (F12) and check for errors

### 7.3 Test from Telegram

1. **Configure BotFather**:
   - Open [@BotFather](https://t.me/BotFather)
   - Send `/mybots`
   - Select your bot
   - **Bot Settings** → **Menu Button** → **Configure menu button**
   - Button text: `📊 Weekly Report` (or `👥 Community`)
   - Web App URL: `https://xaana.club/`

2. **Test in Telegram**:
   - Open your bot
   - Click the menu button
   - The web app should load

---

## Step 8: Troubleshooting

### Container not starting webapp

Check logs:
```bash
docker compose logs zana-prod | grep -i webapp
```

If webapp server is not starting, you may need to enable it in `planner_bot.py` (see Step 3).

### Nginx 502 Bad Gateway

This means nginx can't reach the backend. Check:

```bash
# Is the container running?
docker compose ps

# Is port 8080 listening?
sudo ss -tlnp | grep 8080

# Can nginx reach it?
curl http://localhost:8080/api/health
```

### SSL Certificate Issues

```bash
# Check certificate status
sudo certbot certificates

# Test renewal
sudo certbot renew --dry-run
```

### DNS Not Resolving

Wait longer for DNS propagation, or check:
```bash
# From your local machine
dig xaana.club +short
nslookup xaana.club
```

---

## Quick Reference Commands

```bash
# View container logs
docker compose logs -f zana-prod

# Restart container
docker compose restart zana-prod

# Rebuild and restart
docker compose build zana-prod
docker compose up -d zana-prod

# Manual frontend build and restart (when changes aren't appearing)
cd /opt/zana-bot/zana_planner/webapp_frontend
sudo npm run build
cd ..
sudo docker compose restart zana-webapp

# Check nginx status
sudo systemctl status nginx
sudo nginx -t

# Check SSL certificate
sudo certbot certificates

# Test endpoints
curl https://xaana.club/api/health
curl https://xaana.club/api/public/users?limit=10
```

---

## Summary

**What you need to do:**

1. ✅ **DNS**: Point `xaana.club` A record to `34.163.204.33` on Namecheap
2. ✅ **Deploy code**: Push latest code to VM and rebuild Docker image
3. ✅ **Enable webapp**: Uncomment webapp server code in `planner_bot.py` and rebuild
4. ✅ **Nginx**: Install nginx on host, configure proxy to `localhost:8080`
5. ✅ **SSL**: Get Let's Encrypt certificate with certbot
6. ✅ **Firewall**: Open ports 80 and 443 in GCP firewall
7. ✅ **BotFather**: Configure menu button with `https://xaana.club/`

**Nginx setup**: Yes, you need nginx on the **host** (not in Docker) for SSL/HTTPS. The Docker container runs the FastAPI backend on port 8080, and nginx proxies from port 80/443 to 8080.

