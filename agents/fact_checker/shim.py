import os
import requests
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from agents.common.mcp_bus_client import MCPBusClient

# Config
EXTERNAL_URL = os.getenv("FACT_CHECKER_EXTERNAL_URL", "http://host.docker.internal:8003")
MCP_BUS_URL = os.getenv("MCP_BUS_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", 8003))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register with MCP Bus exactly like the real agent
    client = MCPBusClient(base_url=MCP_BUS_URL)
    agent_address = f"http://localhost:{PORT}"
    
    # Register core tools that the original agent exposed
    # Adjust "verify_facts" if the original tool name was different (e.g., 'fact_check')
    # Based on the server API, we are exposing functionality, but we need to match
    # the tool names expected by 'chief_editor' or 'orchestrator'.
    client.register_agent(
        agent_name="fact_checker",
        agent_address=agent_address,
        tools=["verify_claim", "fact_check", "validate_source"] 
    )
    yield

app = FastAPI(lifespan=lifespan)

# Forwarding logic
# The MCP bus calls agents like POST /<tool_name> with payload
@app.post("/{tool_name}")
async def proxy_tool(tool_name: str, payload: dict):
    target_endpoint = "/fact_check" # Default mapping
    
    # Simple mapping logic (can be expanded)
    if tool_name in ["fact_check", "verify_claim"]:
        target_endpoint = "/fact_check"
    
    # Prepare payload for the external server
    # The external server expects FactCheckRequest structure: {fact, context, sources, options}
    # We might need to map incoming MCP tool arguments to this structure.
    # Assuming the MCP caller sends compatible arguments or we pass them as-is if they match.
    # For now, we perform a direct forward for simplicity, but robustness would require mapping.
    
    # Constructing compatible body
    # If payload is just arguments, wrap or extract them.
    # Case: simple forward
    
    try:
        # Check if we need async
        # if tool_name == "fact_check_async": ...
        
        external_url = f"{EXTERNAL_URL}{target_endpoint}"
        print(f"Forwarding {tool_name} to {external_url} with payload {payload}")
        
        # Add API Key if configured in env (for the shim itself to auth against external server)
        headers = {}
        api_key = os.getenv("FACT_CHECKER_API_KEY")
        if api_key:
            headers["X-API-KEY"] = api_key
            
        resp = requests.post(external_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Shim Error: {e}")
        raise HTTPException(status_code=502, detail=f"External server error: {str(e)}")

# Health check
@app.get("/health")
def health():
    return {"status": "ok", "mode": "proxy", "target": EXTERNAL_URL}