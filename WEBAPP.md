# Telegram Mini Web App Setup

This document explains how to configure and deploy the Zana AI Telegram Mini Web App.

## Overview

The web app allows users to view their weekly progress report directly within Telegram, with a beautiful React-based UI that matches the existing bot's visual design.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │  Telegram Bot   │    │   FastAPI Web App Server    │ │
│  │  (polling)      │    │   (port 8080)               │ │
│  │                 │    │   - /api/weekly             │ │
│  │                 │    │   - /api/user               │ │
│  │                 │    │   - React SPA (/)           │ │
│  └────────┬────────┘    └──────────────┬──────────────┘ │
│           │                            │                 │
│           └────────────┬───────────────┘                 │
│                        │                                 │
│                  ┌─────┴─────┐                          │
│                  │  SQLite   │                          │
│                  │  Database │                          │
│                  └───────────┘                          │
└─────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Web App Configuration (optional, defaults shown)
WEBAPP_ENABLED=true      # Enable/disable web app server
WEBAPP_PORT=8080         # Port for web app server
```

### BotFather Setup

To enable the Mini App button in your Telegram bot:

1. **Open BotFather** in Telegram and send `/mybots`

2. **Select your bot** from the list

3. **Configure Menu Button**:
   - Click "Bot Settings"
   - Click "Menu Button"
   - Click "Configure menu button"
   - Enter the button text: `📊 Weekly Report`
   - Enter the Web App URL: `https://your-domain.com/`

4. **Alternative: Inline Button**
   You can also add a Web App button programmatically using:
   ```python
   from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
   
   keyboard = InlineKeyboardMarkup([[
       InlineKeyboardButton(
           "📊 Open Weekly Report",
           web_app=WebAppInfo(url="https://your-domain.com/")
       )
   ]])
   ```

### Domain Requirements

Telegram Mini Apps require:
- **HTTPS** - Your domain must have a valid SSL certificate
- **Public access** - The URL must be accessible from the internet

For local development, you can use:
- [ngrok](https://ngrok.com/) to create a tunnel
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)

## Deployment

### Docker Compose

The web app is automatically built and served when using Docker:

```bash
# Build and start (includes web app)
docker-compose up -d zana-prod

# The web app will be available at:
# Production: http://your-server:8080
# Staging: http://your-server:8081
```

### Reverse Proxy (Nginx)

For production, set up a reverse proxy with SSL:

```nginx
server {
    listen 443 ssl http2;
    server_name webapp.your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
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
    }
}
```

## Development

### Running Locally

1. **Start the backend** (with web app):
   ```bash
   cd tm_bot
   python -m planner_bot
   # Web app will be at http://localhost:8080
   ```

2. **Start the frontend dev server** (with hot reload):
   ```bash
   cd webapp_frontend
   npm install
   npm run dev
   # Dev server at http://localhost:5173 (proxies API to :8080)
   ```

3. **Build frontend for production**:
   ```bash
   cd webapp_frontend
   npm run build
   # Output in webapp_frontend/dist/
   ```

### Testing Without Telegram

For development, you can test without Telegram by setting mock auth data:

```javascript
// In browser console
localStorage.setItem('dev_init_data', 'user=%7B%22id%22%3A123456%7D&auth_date=1234567890&hash=abc123');
```

Note: This only works in development mode and won't validate against the real bot token.

## API Reference

### GET /api/health
Health check endpoint (no auth required).

**Response:**
```json
{
  "status": "healthy",
  "service": "zana-webapp"
}
```

### GET /api/weekly
Get weekly report for the authenticated user.

**Headers:**
- `X-Telegram-Init-Data`: Telegram WebApp initData string

**Response:**
```json
{
  "week_start": "2024-01-15T00:00:00",
  "week_end": "2024-01-21T23:59:59",
  "total_promised": 20.0,
  "total_spent": 15.5,
  "promises": {
    "learn-rust": {
      "text": "Learn Rust programming",
      "hours_promised": 10.0,
      "hours_spent": 8.5,
      "sessions": [
        {"date": "2024-01-15", "hours": 2.0},
        {"date": "2024-01-17", "hours": 3.5}
      ]
    }
  }
}
```

### GET /api/user
Get user info for the authenticated user.

**Headers:**
- `X-Telegram-Init-Data`: Telegram WebApp initData string

**Response:**
```json
{
  "user_id": 123456789,
  "timezone": "Europe/Paris",
  "language": "en"
}
```

## Security

The web app uses Telegram's [initData validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app) to authenticate users:

1. Telegram provides a signed `initData` string when opening the Mini App
2. The backend validates this signature using HMAC-SHA256 with the bot token
3. The `auth_date` is checked to prevent replay attacks (24-hour window)

This ensures that only authenticated Telegram users can access their data.

## Troubleshooting

### "Authentication failed" error
- Ensure the web app is opened from Telegram, not directly in a browser
- Check that `BOT_TOKEN` environment variable is set correctly
- Verify the domain is configured in BotFather

### Web app not loading
- Check Docker logs: `docker logs zana-prod`
- Verify port 8080 is exposed and accessible
- Ensure HTTPS is properly configured if using a domain

### Blank screen after loading
- Open browser dev tools and check for JavaScript errors
- Verify the React build was successful: `ls webapp_frontend/dist/`
- Check that static files are being served: `curl http://localhost:8080/`
