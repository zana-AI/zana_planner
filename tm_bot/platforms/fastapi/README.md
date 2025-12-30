# FastAPI Platform Adapter for Telegram Mini App

This module provides a FastAPI-based platform adapter that enables the bot to work through HTTP/WebSocket APIs, making it perfect for Telegram Mini Apps and other web integrations.

## Features

- **HTTP API Endpoints**: Send messages and receive bot responses via REST API
- **WebSocket Support**: Real-time bidirectional communication
- **Telegram Authentication**: Validates Telegram Mini App initData
- **Response Storage**: Stores responses for polling fallback
- **Platform Abstraction**: Uses the same platform abstraction layer as other adapters

## Quick Start

### 1. Create and Run the FastAPI App

```python
import os
from platforms.fastapi import create_bot_api

# Configuration
ROOT_DIR = os.getenv("ROOT_DIR", "/path/to/user/data")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STATIC_DIR = os.getenv("STATIC_DIR", None)  # Optional: path to React build

# Create FastAPI app with bot endpoints
app = create_bot_api(
    root_dir=ROOT_DIR,
    bot_token=BOT_TOKEN,
    static_dir=STATIC_DIR
)

# Run with uvicorn
# uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Run with Uvicorn

```bash
# Set environment variables
export ROOT_DIR=/path/to/user/data
export TELEGRAM_BOT_TOKEN=your_bot_token

# Run the server
uvicorn tm_bot.platforms.fastapi.run_server:app --host 0.0.0.0 --port 8000
```

Or create a simple run script:

```python
# run_fastapi_bot.py
import os
import uvicorn
from platforms.fastapi import create_bot_api

if __name__ == "__main__":
    app = create_bot_api(
        root_dir=os.getenv("ROOT_DIR", "/tmp/zana_data"),
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
    )
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## API Endpoints

### POST `/api/bot/message`

Send a message to the bot.

**Headers:**
- `X-Telegram-Init-Data`: Telegram initData string (or `Authorization: Bearer <initData>`)

**Request Body:**
```json
{
  "text": "Hello, add a task to exercise 30 minutes daily",
  "message_id": 123  // Optional
}
```

**Response:**
```json
{
  "success": true,
  "response_id": "1",
  "message": "Message processed"
}
```

### GET `/api/bot/responses`

Get bot responses for the authenticated user.

**Headers:**
- `X-Telegram-Init-Data`: Telegram initData string

**Query Parameters:**
- `since` (optional): ISO timestamp to get responses since that time

**Response:**
```json
{
  "responses": [
    {
      "type": "text",
      "text": "Task created successfully!",
      "keyboard": {
        "buttons": [[{"text": "View Tasks", "callback_data": "view_tasks"}]]
      },
      "timestamp": "2025-12-30T16:00:00"
    }
  ],
  "count": 1
}
```

### DELETE `/api/bot/responses`

Clear stored responses for the user.

**Headers:**
- `X-Telegram-Init-Data`: Telegram initData string

**Response:**
```json
{
  "success": true,
  "message": "Responses cleared"
}
```

### WebSocket `/api/bot/ws`

Real-time bidirectional communication with the bot.

**Connection:**
```
ws://your-domain.com/api/bot/ws?initData=<telegram_init_data>
```

**Client Messages:**
```json
{
  "type": "message",
  "text": "Hello, bot!"
}
```

**Server Messages:**
```json
{
  "type": "response",
  "text": "Hello! How can I help you?",
  "keyboard": {...},
  "timestamp": "2025-12-30T16:00:00"
}
```

**Connection Status:**
```json
{
  "type": "connected",
  "user_id": 123456,
  "message": "Connected to bot"
}
```

## Frontend Integration (React Example)

### Using HTTP API

```typescript
// Send a message
async function sendMessage(text: string) {
  const initData = window.Telegram.WebApp.initData;
  
  const response = await fetch('/api/bot/message', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
    },
    body: JSON.stringify({ text }),
  });
  
  const result = await response.json();
  return result;
}

// Poll for responses
async function getResponses(since?: string) {
  const initData = window.Telegram.WebApp.initData;
  const url = since 
    ? `/api/bot/responses?since=${since}`
    : '/api/bot/responses';
  
  const response = await fetch(url, {
    headers: {
      'X-Telegram-Init-Data': initData,
    },
  });
  
  return await response.json();
}
```

### Using WebSocket

```typescript
// Connect to WebSocket
function connectBotWebSocket() {
  const initData = window.Telegram.WebApp.initData;
  const ws = new WebSocket(
    `wss://your-domain.com/api/bot/ws?initData=${encodeURIComponent(initData)}`
  );
  
  ws.onopen = () => {
    console.log('Connected to bot');
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'response') {
      // Display bot response
      displayBotMessage(data.text, data.keyboard);
    } else if (data.type === 'connected') {
      console.log('Bot connected:', data.user_id);
    }
  };
  
  // Send message
  function sendMessage(text: string) {
    ws.send(JSON.stringify({
      type: 'message',
      text: text,
    }));
  }
  
  return { ws, sendMessage };
}
```

## Architecture

```
┌─────────────────┐
│  Telegram Mini  │
│      App        │
│   (Frontend)    │
└────────┬────────┘
         │
         │ HTTP/WebSocket
         │
┌────────▼─────────────────┐
│   FastAPI Platform       │
│   Adapter                │
│  - HTTP Endpoints        │
│  - WebSocket Server      │
│  - Auth Validation       │
└────────┬─────────────────┘
         │
         │ Uses
         │
┌────────▼─────────────────┐
│   PlannerBot              │
│  (Platform-Agnostic)      │
│  - Message Handlers       │
│  - LLM Integration        │
│  - Task Management        │
└───────────────────────────┘
```

## Authentication

The FastAPI adapter uses Telegram Mini App authentication. The `initData` from `window.Telegram.WebApp.initData` is validated using HMAC-SHA256 with the bot token.

**Security Notes:**
- Always use HTTPS in production
- Validate `initData` on every request
- `initData` expires after 24 hours (configurable)
- Never expose bot token to frontend

## Error Handling

All endpoints return standard HTTP status codes:

- `200`: Success
- `400`: Bad Request (invalid input)
- `401`: Unauthorized (invalid or missing auth)
- `500`: Internal Server Error

Error responses:
```json
{
  "detail": "Error message"
}
```

## Development

### Testing Locally

1. Set up environment variables:
```bash
export ROOT_DIR=/tmp/zana_test_data
export TELEGRAM_BOT_TOKEN=your_test_token
```

2. Run the server:
```bash
uvicorn tm_bot.platforms.fastapi.run_server:app --reload
```

3. Test with curl:
```bash
# Send message
curl -X POST http://localhost:8000/api/bot/message \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Init-Data: <your_init_data>" \
  -d '{"text": "Hello"}'
```

### Integration with Existing Webapp

The FastAPI adapter extends the existing `webapp/api.py`. You can use both:

```python
from webapp.api import create_webapp_api
from platforms.fastapi import add_bot_routes, FastAPIPlatformAdapter

# Create base webapp
app = create_webapp_api(root_dir, bot_token, static_dir)

# Add bot routes
bot_adapter = FastAPIPlatformAdapter(app=app)
# ... initialize bot and handlers ...
add_bot_routes(app, bot_adapter, handler_wrapper)
```

## Limitations

- WebSocket connections are stored in memory (not suitable for horizontal scaling without Redis)
- Responses are stored in memory (consider Redis for production)
- No rate limiting (add middleware for production)

## Production Considerations

1. **Scaling**: Use Redis for WebSocket connections and response storage
2. **Rate Limiting**: Add rate limiting middleware
3. **Caching**: Cache user settings and frequently accessed data
4. **Monitoring**: Add logging and monitoring
5. **Security**: Use HTTPS, validate all inputs, sanitize outputs

## Example: Full Integration

See `run_server.py` for a complete example of running the FastAPI bot server.


