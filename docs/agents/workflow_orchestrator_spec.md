# Workflow Orchestration Agent Specification

## 1. Overview
The **Workflow Orchestrator Agent** acts as the central coordinator for the JustNews data pipeline. It is responsible for monitoring the state of data as it initiates in the system, checking hardware resource availability, and orchestrating work across functional agents (Analyst, Synthesizer, etc.) by polling database state flags and dispatching commands via the MCP Bus.

**Location**: `agents/workflow_orchestrator/`  
**Port**: `8020` (Proposed)

## 2. Motivation
Currently, the system relies on point-to-point triggers or manual intervention. A central orchestrator decouples the "business logic" of the pipeline flow from the functional agents, allowing for:
- **Better Flow Control**: Managing backpressure when the system is under load.
- **Resource Awareness**: Preventing GPU saturation by gating heavy analysis tasks.
- **Visibility**: A single place to define "what happens next" for any given data state.

## 3. Architecture

### 3.1. Core Components
The agent will be built using the standard FastAPI + MCP Bus integration pattern, augmented with a background loop engine.

1.  **Orchestrator Engine (`engine.py`)**:
    - Runs a continuous event loop (using `asyncio`).
    - Executes defined **Workflows** at configurable intervals.
2.  **Resource Monitor (`resources.py`)**:
    - Checks system vital signs (CPU Load, RAM usage, GPU Memory/Utilization).
    - Implementing "Red/Yellow/Green" pressure status to throttle job dispatch.
3.  **Policy Manager (`policies.py`)**:
    - Defines the criteria for transitioning data (e.g., "If article is ingested AND NOT analyzed AND GPU < 80% load, THEN trigger Analyst").
4.  **Task Dispatcher**:
    - Utilizes `MCPBusClient` to send commands to other agents.

### 3.2. Data Flow
1.  **Poll**: The Engine queries the MariaDB database for items requiring attention (e.g., `SELECT id FROM articles WHERE analyzed = FALSE`).
2.  **Check Resources**: The Engine consults the Resource Monitor.
3.  **Decide**: If resources allow, a batch of items is selected.
4.  **Dispatch**: The Engine calls the appropriate agent via MCP Bus (e.g., `POST http://analyst/analyze_article`).
5.  **Observe**: (Optional) The Engine tracks the task ID or awaits completion if synchronous (prefer asynchronous fire-and-forget with state updates handled by the worker agent).

## 4. Workflows

### 4.1. Stage 2 -> Stage 3 (Analysis Backfill)
*   **Trigger Condition**: `articles.analyzed == 0`
*   **Target Agent**: `analyst`
*   **Action**: Call `analyze_article(article_id)`
*   **Batch Size**: Dynamic (default 5-10 concurrent requests).

### 4.2. Stage 2B -> Stage 2C (Embedding Backfill)
*   **Trigger Condition**: `articles.analyzed == 1` AND `articles.embedded == 0`
*   **Target Agent**: `memory`
*   **Action**: Call `embed_article(article_id)`
*   **Batch Size**: Dynamic.

### 4.3. Stage 3 -> Stage 4 (Synthesize/Publish) -- *Future*
*   **Trigger Condition**: `articles.analyzed == 1` AND `articles.synthesized == 0`
*   **Target Agent**: `synthesizer` / `chief_editor`
*   **Action**: Call generation tasks.

## 5. Implementation Specification

### 5.1. File Structure
```text
agents/workflow_orchestrator/
├── __init__.py
├── main.py              # FastAPI app, MCP Registration, Startup/Shutdown hooks
├── engine.py            # The main async loop implementation
├── policies.py          # Definitions of workflows (SQL Queries -> Agent Actions)
├── resources.py         # Hardware stats (psutil, NVML wrappers)
└── tools.py             # Tools exposed to MCP (e.g., "force_run_workflow")
```

### 5.2. Configuration (`config/system_config.json` addition)
```json
"orchestrator": {
  "polling_interval_seconds": 10,
  "max_concurrent_tasks": 5,
  "resource_limits": {
    "max_cpu_percent": 80,
    "max_gpu_memory_percent": 90
  }
}
```

### 5.3. Key Classes

#### `WorkflowPolicy`
Abstract base class for a pipeline rule.
```python
class WorkflowPolicy(ABC):
    async def check_condition(self, db_session) -> list[int]:
        """Return list of IDs needing processing."""
        pass
        
    async def execute(self, item_ids: list[int], mcp_client):
        """Dispatch tasks to agents."""
        pass
```

## 6. Development Plan
1.  **Scaffold**: Create directory and `main.py` with MCP registration.
2.  **Resource Monitor**: Implement `resources.py` using `psutil` and existing `gpu_utils`.
3.  **Engine**: Build the async loop to iterate over policies.
4.  **Implement Policy 1**: `IngestionToAnalysisPolicy` (The "Backfill" logic).
5.  **Test**: Verify it picks up unanalyzed articles and triggers the Analyst.
```
