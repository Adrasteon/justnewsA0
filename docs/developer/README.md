# JustNews Developer Documentation

## Quick Links

- [Code Index + Memory Playbook](CODE_INDEX_MEMORY_PLAYBOOK.md)

## Architecture Overview

JustNews is a distributed multi-agent system for automated news analysis, featuring GPU acceleration, continuous
learning, and comprehensive monitoring.

## System Architecture

### Core Components

#### MCP Bus (Model Context Protocol Bus)

- **Role**: Central communication hub coordinating all agents

- **Technology**: FastAPI with async message passing

- **Port**: 8000

- **Responsibilities**:

- Agent registration and discovery

- Inter-agent communication routing

- Health monitoring and load balancing

- Message queuing and reliability

#### Specialized Agents

Each agent is a microservice with specific responsibilities:

- **Chief Editor (Port 8001)**: Workflow orchestration and system coordination

- **Scout (Port 8002, deprecated)**: Legacy content discovery service (do not use)

- **Fact Checker Shim (Port 8018)**: Active fact-check endpoint; forwards to external backend (`FACT_CHECKER_EXTERNAL_URL`, currently `http://localhost:8003`)

- **Analyst (Port 8004)**: GPU-accelerated sentiment and bias analysis

- **Synthesizer (Port 8005)**: Content synthesis and summarization

- **Critic (Port 8006)**: Quality assessment and review

- **Memory (Port 8007)**: Data persistence and vector search

- **Reasoning (Port 8008)**: Symbolic logic and reasoning

#### Supporting Services

- **Dashboard (Port 8013)**: Web interface and real-time monitoring

- **Public API (Port 8014)**: External API for news data access

- **Archive API (Port 8021)**: RESTful archive with legal compliance

- **GraphQL API (Port 8020)**: Advanced query interface

### Data Flow Architecture

```

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   News Sources  │───▶│     Scout       │───▶│    Fact Checker │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Analyst      │◀───│  Chief Editor   │───▶│     Memory      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Synthesizer    │    │     Critic      │    │   Reasoning     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              └────────────────────────┘
                                       │
                                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Public APIs   │    │   Dashboard     │    │   Monitoring    │
└─────────────────┘    └─────────────────┘    └─────────────────┘

```

### Technology Stack

#### Core Framework

- **FastAPI**: High-performance async web framework

- **Pydantic V2**: Type-safe data validation and serialization

- **SQLAlchemy**: Database ORM with async support

- **Redis**: Caching and session management

#### AI/ML Stack

- **PyTorch 2.6+**: Deep learning framework with CUDA 12.4

- **Transformers**: Pre-trained models and tokenizers

- **Sentence Transformers**: Text embedding and similarity

- **TensorRT**: GPU inference optimization

- **NVIDIA MPS**: GPU memory sharing and isolation

#### Data Processing

- **MariaDB**: Primary relational data storage

- **ChromaDB**: Vector similarity search and embeddings

- **Pandas/Polars**: Data manipulation and analysis

- **NumPy**: Numerical computing

#### Infrastructure

- **Docker**: Containerization

- **Kubernetes**: Container orchestration

- **Prometheus/Grafana**: Monitoring and alerting

- **Nginx**: Reverse proxy and load balancing

## Agent Development Guide

### Agent Structure Pattern

All agents follow a consistent structure:

```bash

agents/{agent_name}/
├── __init__.py
├── main.py              # FastAPI application
├── tools.py             # Agent-specific tools
├── models.py            # Pydantic models
├── config.py            # Agent configuration
├── requirements.txt     # Dependencies
└── tests/
    ├── __init__.py
    ├── test_main.py
    └── test_tools.py

```

### Agent Implementation Template

```python

## agents/my_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import asyncio

from common.mcp_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.config import get_config

## Configure logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

## Initialize components

app = FastAPI(title="My Agent", version="1.0.0")
config = get_config()
metrics = JustNewsMetrics(agent="my_agent")
mcp_client = MCPBusClient()

## Pydantic models

class ToolCall(BaseModel):
    """Standard MCP tool call format"""
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: float

## Global state

start_time = asyncio.get_event_loop().time()

@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    try:
        # Register with MCP Bus
        await mcp_client.register_agent(
            name="my_agent",
            endpoint=f"http://localhost:{config.port}",
            capabilities=["my_tool"]
        )
        logger.info("Agent registered with MCP Bus")
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        raise

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime=asyncio.get_event_loop().time() - start_time
    )

@app.post("/my_tool")
async def my_tool_endpoint(call: ToolCall):
    """Main tool endpoint"""
    try:
        # Record metrics
        metrics.increment("tool_calls", {"tool": "my_tool"})

        # Execute tool logic
        result = await my_tool_function(*call.args, **call.kwargs)

        # Record success
        metrics.increment("tool_success", {"tool": "my_tool"})

        return {
            "status": "success",
            "data": result,
            "timestamp": asyncio.get_event_loop().time()
        }

    except Exception as e:
        # Record error
        metrics.increment("tool_errors", {"tool": "my_tool", "error": str(e)})
        logger.error(f"Tool execution failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {str(e)}"
        )

## Tool implementation

async def my_tool_function(param1: str, param2: int = 0) -> Dict[str, Any]:
    """Implement your tool logic here"""
    # Example implementation
    return {
        "param1": param1,
        "param2": param2,
        "result": f"Processed {param1} with {param2}"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.port,
        reload=config.debug
    )

```bash

### MCP Bus Integration

#### Agent Registration

```python
from common.mcp_client import MCPBusClient

mcp_client = MCPBusClient()

## Register agent

await mcp_client.register_agent(
    name="my_agent",
    endpoint="http://localhost:8009",
    capabilities=["tool1", "tool2"]
)

```

#### Inter-Agent Communication

```python

## Call another agent
