# JustNews API Documentation

## Overview

JustNews provides multiple REST APIs for different system components and user interactions. All APIs follow RESTful
principles with JSON request/response formats.

## API Architecture

### Service Ports

- **MCP Bus**: Port 8000 - Central communication hub for inter-agent communication

- **Chief Editor**: Port 8001 - Workflow orchestration and system coordination

- **Scout**: Port 8004 - Content discovery and web crawling

- **Fact Checker**: Port 8003 - Source verification and fact-checking

- **Analyst**: Port 8004 - GPU-accelerated sentiment and bias analysis

- **Synthesizer**: Port 8005 - Content synthesis and summarization

- **Critic**: Port 8006 - Quality assessment and review

- **Memory**: Port 8007 - Data persistence and vector search

- **Reasoning**: Port 8008 - Symbolic logic and reasoning

- **Dashboard**: Port 8013 - Web interface and monitoring

- **Public API**: Port 8014 - External API for news data access

- **Archive API**: Port 8021 - RESTful archive access with legal compliance

- **GraphQL API**: Port 8020 - Advanced query interface

### Authentication & Security

- **API Keys**: Required for external API access in some research or legacy flows

- **JWT Tokens**: Used for authenticated sessions; `agents/common/auth_api`issues tokens. Admin endpoints accept a valid
  JWT with`role=admin`when`ADMIN_API_KEY` is not configured.

- **ADMIN API Key (legacy)**: For simple single-host deployments or scripted operations a static `ADMIN_API_KEY`may be
  set; admin endpoints accept it via`Authorization: Bearer <ADMIN_API_KEY>`or`X-Admin-API-Key: <key>`. Use JWTs for
  multi-user production setups.

- **Rate Limiting**: Implemented on public endpoints; production deployments should set `REDIS_URL` to use a Redis-
  backed limiter across replicas.

- **CORS**: Configured for web application access

### Response Format

All APIs return JSON responses with consistent error handling:

```json
{
  "status": "success|error",
  "data": { ... },
  "message": "Optional message",
  "timestamp": "ISO 8601 timestamp"
}

```bash

## Core APIs

### MCP Bus API (Port 8000)

Central communication hub for inter-agent messaging.

#### Endpoints

- `POST /register` - Register a new agent with the bus

- `POST /call` - Send a message to an agent

- `GET /agents` - List all registered agents

- `GET /health` - Health check endpoint

- `GET /ready` - Readiness check endpoint

- `GET /metrics` - Prometheus metrics endpoint

#### Example Usage

```bash

## Register an agent

curl -X POST <http://localhost:8000/register> \
  -H "Content-Type: application/json" \
  -d '{"agent": "scout", "endpoint": "http://localhost:8004"}'

## Call an agent

curl -X POST <http://localhost:8000/call> \
  -H "Content-Type: application/json" \
  -d '{"agent": "memory", "tool": "save_article", "args": ["article_data"]}'

```

### Memory Agent API (Port 8007)

Data persistence and retrieval with vector search capabilities.

#### Endpoints

- `POST /save_article` - Store an article with metadata

- `POST /get_article` - Retrieve article by ID

- `POST /vector_search_articles` - Semantic search through articles

- `POST /get_recent_articles` - Get recently processed articles

- `POST /embed_article` - Embed article content and update DB flag

- `GET /get_article_count` - Get total article count

- `POST /get_sources` - Get available news sources

#### Example Usage

```bash

## Save an article

curl -X POST <http://localhost:8007/save_article> \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Breaking News",
    "content": "Article content...",
    "source": "news_source",
    "published_date": "2025-10-22T10:00:00Z"
  }'

## Vector search

curl -X POST <http://localhost:8007/vector_search_articles> \
  -H "Content-Type: application/json" \
  -d '{"query": "climate change", "limit": 10}'

```bash

### Public API (Port 8014)

External API for accessing processed news data.

#### Endpoints

- `GET /articles` - Search and filter articles

- `GET /articles/{id}` - Get specific article

- `GET /sources` - List available sources

- `GET /categories` - Get content categories

- `POST /search` - Advanced search with filters

#### Authentication

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  <http://localhost:8014/articles?limit=10>

```

### Archive API (Port 8021)

RESTful API for archive access with legal compliance features.

#### Endpoints

- `GET /articles` - GDPR-compliant article access

- `POST /consent` - Manage user consent

- `DELETE /data` - Right to be forgotten implementation

- `GET /export` - Data export functionality

- `GET /audit` - Compliance audit logs

### GraphQL API (Port 8020)

Advanced query interface for complex data relationships.

#### Schema Highlights

```graphql
type Query {
  articles(filter: ArticleFilter, limit: Int): [Article]
  article(id: ID!): Article
  sources: [Source]
  search(query: String!, filters: SearchFilters): SearchResult
}

type Article {
  id: ID!
  title: String!
  content: String!
  source: Source!
  publishedDate: DateTime!
  sentiment: SentimentAnalysis
  entities: [Entity]
}

```

## Agent-Specific APIs

### Scout Agent (Port 8004)

Content discovery and web crawling.

- `POST /crawl` - Initiate content crawling

- `GET /status` - Crawling status and progress

- `POST /sources` - Manage news sources

### Analyst Agent (Port 8004)

GPU-accelerated analysis.

- `POST /analyze` - Sentiment and bias analysis

- `GET /models` - Available analysis models

- `GET /gpu_status` - GPU utilization metrics

### Synthesizer Agent (Port 8005)

Content synthesis and summarization.

- `POST /summarize` - Generate article summaries

- `POST /topics` - Topic modeling and clustering

- `GET /models` - Available synthesis models

## Error Handling

### HTTP Status Codes

- `200` - Success

- `400` - Bad Request (invalid parameters)

- `401` - Unauthorized (missing/invalid authentication)

- `403` - Forbidden (insufficient permissions)

- `404` - Not Found

- `429` - Too Many Requests (rate limited)

- `500` - Internal Server Error

- `503` - Service Unavailable

### Error Response Format

```json
{
  "status": "error",
  "message": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": { ... },
  "timestamp": "2025-10-22T10:00:00Z"
}

```

## Rate Limiting

### Limits

- **Public API**: 1000 requests/hour per API key

- **Archive API**: 100 requests/hour per user

- **GraphQL API**: 5000 queries/hour per user

### Headers

```yaml

X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1634900000

### Redis & multi-replica rate limiting

- To enable consistent rate limiting across replicas, set `REDIS_URL` in your environment (e.g. `redis://:password@redis:6379/0`).

- The public search router in `agents/dashboard/search_api.py` prefers a Redis-backed limiter (fixed-window INCR+EXPIRE) and falls back to the in-memory limiter when `REDIS_URL` is not configured.

- For high-volume production systems where exact token-bucket semantics and per-request atomicity are required, implement a Redis Lua script to perform atomic INCR+EXPIRE operations.

- Alternatively, use a dedicated rate limiter proxy such as Kong or Envoy (with a Redis-backed rate limiter) for scalable enforcement.

```

## SDKs & Client Libraries

### Python Client

```python
from justnews_client import JustNewsClient

client = JustNewsClient(api_key="your_key")
articles = client.search_articles("climate change", limit=10)

```

### JavaScript Client

```javascript
import { JustNewsAPI } from 'justnews-api';

const client = new JustNewsAPI({ apiKey: 'your_key' });
const articles = await client.search('climate change');

```

## Versioning

API versioning follows semantic versioning:

- **v1** - Current stable version

- **Breaking Changes** - New major version

- **Backwards Compatible** - Minor version increments

---

*API Documentation Version: 1.0.0* *Last Updated: October 22, 2025*
