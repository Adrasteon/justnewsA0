# FastAPI Best Practices Guide

## Overview

This guide provides best practices for developing FastAPI applications in the JustNews system, incorporating the latest
FastAPI patterns and conventions.

## Application Structure

### Basic Application Setup

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

## Create FastAPI application with metadata

app = FastAPI(
    title="JustNews API",
    description="Multi-agent news analysis system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

## Add middleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure for production
)

```bash

### Path Operations

#### GET Endpoints

```python
from typing import Optional, List
from fastapi import Query, Path

@app.get("/")
async def read_root():
    """Root endpoint returning API information"""
    return {"message": "JustNews API", "version": "1.0.0"}

@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(..., gt=0, description="The ID of the item"),
    q: Optional[str] = Query(None, max_length=50, description="Search query")
):
    """Retrieve an item by ID with optional search"""
    return {"item_id": item_id, "q": q}

@app.get("/items/")
async def read_items(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """Retrieve paginated list of items"""
    return {"skip": skip, "limit": limit}

```

#### POST Endpoints

```python
from pydantic import BaseModel, Field
from typing import Optional

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price: float = Field(..., gt=0)
    tax: Optional[float] = Field(None, ge=0)

@app.post("/items/", response_model=ItemCreate)
async def create_item(item: ItemCreate):
    """Create a new item"""
    # Process item creation
    return item

```yaml

#### PUT/PATCH Endpoints

```python
from pydantic import BaseModel

class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    tax: Optional[float] = Field(None, ge=0)

@app.put("/items/{item_id}")
async def update_item(
    item_id: int = Path(..., gt=0),
    item: ItemUpdate = ...
):
    """Update an existing item"""
    # Process item update
    return {"item_id": item_id, "updated": True}

```

## Request Body Handling

### Pydantic Models

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    full_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email address')
        return v

class Article(BaseModel):
    title: str
    content: str
    author: User
    tags: List[str] = []
    published: bool = False

```yaml

### Nested Models

```python
class Comment(BaseModel):
    content: str
    author: User
    replies: List['Comment'] = []

Comment.update_forward_refs()  # Required for self-referencing models

```

## Dependency Injection

### Basic Dependencies

```python
from fastapi import Depends, HTTPException
from typing import Generator

## Database dependency

def get_db() -> Generator:
    db = create_database_session()
    try:
        yield db
    finally:
        db.close()

@app.get("/items/")
async def read_items(db = Depends(get_db)):
    """Retrieve items with database dependency"""
    return db.query(Item).all()

```bash

### Security Dependencies

```python
from fastapi.security import OAuth2PasswordBearer, HTTPBearer
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
bearer_scheme = HTTPBearer()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current authenticated user"""
    # Validate token and return user
    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

### Admin endpoints & reload protection

When registering runtime control endpoints (for example `/admin/reload` or feature toggles), prefer role-based JWTs (admin role) or a short-lived service token handled by your gateway or auth layer.

For example, the helper `agents.common.reload.register_reload_endpoint(app, require_admin=True)` enables a small `/admin/reload` endpoint.

When `require_admin=True`, the endpoint accepts either:

- a static `ADMIN_API_KEY` header (for compatibility), or
- a bearer JWT with `role=admin` verified via `agents/common/auth_api.verify_token`.

This pattern avoids exposing sensitive runtime controls to anonymous or public traffic and centralizes auth logic for reload operations.

async def get_current_active_user(current_user = Depends(get_current_user)):
    """Ensure user is active"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

@app.get("/users/me")
async def read_users_me(current_user = Depends(get_current_active_user)):
    """Protected endpoint requiring active user"""
    return current_user

```

## Error Handling

### Custom Exceptions

```python
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any

class CustomException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    """Handle custom exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )

## Usage

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    item = get_item(item_id)
    if not item:
        raise CustomException("Item not found", status_code=404)
    return item

```bash

### Validation Error Handling

```python
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors()
        }
    )

```

## Response Models

### Response Model Definition

```python
from pydantic import BaseModel
from typing import List, Optional

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float

class ItemsResponse(BaseModel):
    items: List[ItemResponse]
    total: int
    skip: int
    limit: int

@app.get("/items/", response_model=ItemsResponse)
async def read_items(skip: int = 0, limit: int = 100):
    """Retrieve paginated items with response model"""
    items = get_items(skip, limit)
    return {
        "items": items,
        "total": len(items),
        "skip": skip,
        "limit": limit
    }

```bash

### Different Response Models

```python
class ItemPublic(ItemResponse):
    """Public item data (excludes sensitive fields)"""
    pass

class ItemPrivate(ItemResponse):
    """Private item data (includes all fields)"""
    internal_notes: Optional[str]

@app.get("/items/{item_id}/public", response_model=ItemPublic)
async def read_item_public(item_id: int):
    """Public item endpoint"""
    return get_item(item_id)

@app.get("/items/{item_id}/private", response_model=ItemPrivate)
async def read_item_private(item_id: int, current_user = Depends(get_current_user)):
    """Private item endpoint (authenticated users only)"""
    return get_item(item_id, include_private=True)

```

## Middleware

### Custom Middleware

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Custom logging middleware"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        logger.info(f"Request: {request.method} {request.url}")

        response = await call_next(request)

        # Log response
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} in {process_time:.3f}s")

        return response

## Add to app

app.add_middleware(LoggingMiddleware)

```bash

### Rate Limiting Middleware

```python
from collections import defaultdict
import time
from fastapi import HTTPException

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()

        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if now - req_time < 60
        ]

        # Check rate limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Add current request
        self.requests[client_ip].append(now)

        response = await call_next(request)
        return response

    #### Redis-backed rate limiting

For multi-replica deployments, use a Redis-backed limiter and set `REDIS_URL` in the environment.

Prefer a Redis `INCR` + `EXPIRE` strategy in the application for a fixed-window limiter.

If you require token-bucket semantics, consider either:

- implementing a Lua script that runs in Redis, or
- using a dedicated rate-limiter proxy (e.g., Kong or Envoy).

The repository implements a Redis-backed fallback in `agents/dashboard/rate_limit.py`.

## Background Tasks

### Basic Background Tasks

```python
from fastapi import BackgroundTasks

def send_notification(email: str, message: str):
    """Background task to send notification"""
    # Send email or notification
    pass

@app.post("/items/")
async def create_item(
    item: ItemCreate,
    background_tasks: BackgroundTasks
):
    """Create item with background notification"""
    # Create item
    new_item = create_item_in_db(item)

    # Add background task
    background_tasks.add_task(
        send_notification,
        email="admin@example.com",
        message=f"New item created: {new_item.name}"
    )

    return new_item

```bash

### Task Management

```python
from fastapi import BackgroundTasks
import asyncio

async def process_data_async(data: dict):
    """Async background processing"""
    await asyncio.sleep(1)  # Simulate processing
    # Process data
    pass

@app.post("/process/")
async def process_data(
    data: dict,
    background_tasks: BackgroundTasks
):
    """Process data asynchronously"""
    background_tasks.add_task(process_data_async, data)
    return {"message": "Processing started"}

```

## WebSockets

### Basic WebSocket Endpoint

```python
from fastapi import WebSocket, WebSocketDisconnect
import json

class ConnectionManager:
    """WebSocket connection manager"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    """WebSocket endpoint for real-time communication"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Process message
            response = f"Client {client_id}: {data}"
            await manager.broadcast(response)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

```bash

## Testing

### Test Client Setup

```python
from fastapi.testclient import TestClient
import pytest

@pytest.fixture
def client():
    """Test client fixture"""
    from main import app
    return TestClient(app)

def test_read_root(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "JustNews API", "version": "1.0.0"}

def test_create_item(client):
    """Test item creation"""
    item_data = {
        "name": "Test Item",
        "price": 10.99
    }
    response = client.post("/items/", json=item_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == item_data["name"]
    assert data["price"] == item_data["price"]

```

### Async Testing

```python
import pytest_asyncio

@pytest.mark.asyncio
async def test_async_endpoint():
    """Test async endpoint"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/async-endpoint")
        assert response.status_code == 200

```bash

## Performance Optimization

### Response Caching

```python
from fastapi import Response
from functools import lru_cache
import time

@lru_cache(maxsize=100)
def get_expensive_data_cached(key: str):
    """Cached expensive operation"""
    # Expensive computation
    time.sleep(1)
    return {"data": f"result for {key}"}

@app.get("/cached-data/{key}")
async def get_cached_data(key: str):
    """Endpoint with response caching"""
    data = get_expensive_data_cached(key)
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers={"Cache-Control": "max-age=300"}  # Cache for 5 minutes
    )

```

### Database Optimization

```python
from sqlalchemy.orm import selectinload
from fastapi import Depends

## Optimized query with eager loading

@app.get("/articles/with-authors/")
async def get_articles_with_authors(db = Depends(get_db)):
    """Get articles with authors (optimized)"""
    query = select(Article).options(selectinload(Article.author))
    result = await db.execute(query)
    articles = result.scalars().all()
    return articles

```bash

## Security Best Practices

### Input Validation

```python
from pydantic import validator
import re

class SecureUserInput(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str

    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must be alphanumeric')
        return v

    @validator('email')
    def email_valid(cls, v):
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v

```

### HTTPS and Security Headers

```python
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.gzip import GZipMiddleware

## Force HTTPS

app.add_middleware(HTTPSRedirectMiddleware)

## GZip compression

app.add_middleware(GZipMiddleware, minimum_size=1000)

## Security headers

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

```bash

## Deployment

### Production Server

```python

## For production, use a production ASGI server

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,  # Multiple workers for production
        reload=False  # Disable reload in production
    )

```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

```

---

*FastAPI Best Practices Guide - Version 1.0.0* *Based on FastAPI documentation and latest patterns* *Last Updated:
October 22, 2025*
