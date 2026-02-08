# JustNews User Guides

## Getting Started

Welcome to JustNews! This guide will help you get started based on your role and needs.

## Quick Start by Role

### 👨‍💼 **System Administrator**

If you're setting up or maintaining the JustNews system:

1. **Prerequisites Check**

```bash
   # Verify system requirements
python --version  # Should be 3.11+ nvidia-smi        # GPU verification docker
--version  # Container support ```

1. **Environment Setup**

```bash
# Clone and setup
git clone <repository> cd JustNews ./activate_environment.sh
```

1. **Configuration**

```bash
# Copy and customize configuration
cp config/templates/production.json config/production.json
# Edit with your settings

```bash

1. **Deployment**

```bash
# Start all services
make deploy-production
```

1. **Verification**

```bash
# Check system health
curl <http://localhost:8000/health> curl <http://localhost:8013/dashboard>
```

### 👩‍🔬 **Data Scientist/Researcher**

If you're using JustNews for research or analysis:

1. **API Access Setup**

```python
   # Install client library
pip install justnews-client

   # Initialize client
from justnews_client import JustNewsClient client =
JustNewsClient(api_key="your_research_key") ```

1. **Basic Queries**

```python
# Search for articles
articles = client.search_articles( query="climate change", date_from="2025-01-01", limit=100 )

# Get sentiment analysis
for article in articles: print(f"Sentiment: {article.sentiment.score}")
```

1. **Advanced Analytics**

```python
# Vector search for similar content
similar = client.vector_search( query="renewable energy policies",
similarity_threshold=0.8 )

# Export data for analysis
client.export_articles( query="your research query", format="json",
filename="research_data.json" )
```

### 👨‍💻 **Developer**

If you're developing or extending JustNews:

1. **Development Environment**

```bash
# Setup development environment
make setup-dev make test  # Run test suite
```

1. **Code Structure**

``` agents/           # Individual agent implementations common/           #
Shared utilities and libraries config/           # Configuration management
docs/            # Documentation tests/           # Test suites ```

1. **Adding a New Agent**

```python
# Create agent structure
mkdir agents/new_agent touch agents/new_agent/main.py touch agents/new_agent/__init__.py
```

1. **Testing Your Changes**

```bash
# Run specific tests
pytest tests/test_new_agent.py -v

# Run integration tests
make test-integration
```

## System Administration Guide

### Daily Operations

#### Health Monitoring

```bash

## Check all services

make health-check

## View dashboard

open <http://localhost:8013>

## Check logs

make logs

```

#### Performance Monitoring

```bash

## GPU utilization

nvidia-smi

## System metrics

make metrics

## Performance benchmarks

make benchmark

```

### Maintenance Tasks

#### Database Maintenance

```bash

## Backup database

make db-backup

## Optimize indices

make db-optimize

## Cleanup old data

make db-cleanup

```

#### Model Updates

```bash

## Update ML models

make update-models

## Validate model performance

make validate-models

## Rollback if needed

make rollback-models

```bash

### Troubleshooting

#### Common Issues

**Service Not Starting**

```bash

## Check service status

systemctl status justnews-*

## View service logs

journalctl -u justnews-mcp-bus -f

## Restart service

systemctl restart justnews-mcp-bus

```

**GPU Memory Issues**

```bash

## Check GPU memory

nvidia-smi

## Reset GPU memory

make gpu-reset

## Check MPS status

make mps-status

```bash

**Database Connection Issues**

```bash

## Test database connection

make db-test

## Check connection pool

make db-pool-status

## Restart database service

make db-restart

```

## API Usage Guide

### Authentication

```python

## API Key authentication

import requests

headers = { 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json' }

response = requests.get('http://localhost:8014/articles', headers=headers)

```bash

### Basic Operations

#### Article Search

```python

## Simple search

articles = client.search_articles("artificial intelligence")

## Advanced search with filters

articles = client.search_articles( query="machine learning", sources=["techcrunch", "wired"], date_from="2025-01-01",
sentiment_min=0.5, limit=50 )

```

#### Article Retrieval

```python

## Get specific article

article = client.get_article("article_id_123")

## Get article with analysis

article = client.get_article( "article_id_123", include_sentiment=True, include_entities=True, include_topics=True )

```bash

#### Batch Operations

```python

## Bulk article retrieval

article_ids = ["id1", "id2", "id3"] articles = client.get_articles_batch(article_ids)

## Bulk analysis request

analyses = client.analyze_articles_batch(article_ids, analysis_type="sentiment")

```

### Advanced Features

#### Vector Search

```python

## Semantic search

results = client.vector_search( query="climate change impact on economy", limit=20, similarity_threshold=0.7 )

## Search with filters

results = client.vector_search( query="renewable energy", sources=["bbc", "reuters"], date_range=["2025-01-01",
"2025-12-31"], limit=10 )

```bash

#### Real-time Monitoring

```python

## Subscribe to new articles

client.subscribe_to_feed( query="breaking news", callback=my_callback_function )

## Monitor sentiment trends

trends = client.get_sentiment_trends( topic="election", timeframe="24h" )

```

## Development Guide

### Agent Development

#### Agent Structure

```python
from fastapi import FastAPI from pydantic import BaseModel import logging

app = FastAPI(title="My Agent") logger = logging.getLogger(__name__)

class ToolCall(BaseModel): args: list kwargs: dict

@app.post("/my_tool") def my_tool_endpoint(call: ToolCall): """Implement your tool logic here""" try: result =
my_tool_function(*call.args, **call.kwargs) return {"status": "success", "data": result} except Exception as e:
logger.error(f"Tool failed: {e}") return {"status": "error", "message": str(e)}

```bash

#### MCP Bus Integration

```python
from common.mcp_client import MCPBusClient

## Initialize MCP client

mcp_client = MCPBusClient()

## Register with bus

mcp_client.register_agent("my_agent", "http://localhost:8009")

## Call other agents

result = mcp_client.call_agent( agent="memory", tool="save_article", article_data=my_article )

```

### Testing

#### Unit Tests

```python
import pytest from agents.my_agent.main import my_tool_function

def test_my_tool():
# Arrange
input_data = "test input"

# Act
result = my_tool_function(input_data)

# Assert
assert result is not None assert isinstance(result, dict)

```bash

#### Integration Tests

```python
def test_agent_integration(mcp_server):
# Test with MCP bus
response = requests.post( f"{mcp_server.url}/call", json={ "agent": "my_agent", "tool": "my_tool", "args": ["test"] } )
assert response.status_code == 200

```

### Deployment

#### Local Development

```bash

## Run agent locally

python -m agents.my_agent.main

## Run with hot reload

uvicorn agents.my_agent.main:app --reload --port 8009

```bash

#### Production Deployment

```bash

## Build and deploy as systemd unit (package your code and create a systemd service)

## Example: copy service file and start

sudo cp infrastructure/systemd/units/my-agent.service /etc/systemd/system/ sudo systemctl daemon-reload sudo systemctl
enable --now my-agent

```

## Best Practices

### Performance

- Use async/await for I/O operations

- Implement proper error handling and retries

- Monitor resource usage (CPU, memory, GPU)

- Use connection pooling for databases

### Security

- Validate all input data

- Use parameterized queries

- Implement rate limiting

- Log security events

### Reliability

- Implement health checks

- Use circuit breakers for external calls

- Monitor error rates and latency

- Have rollback procedures ready

---

*User Guides Version: 1.0.0* *Last Updated: October 22, 2025*
