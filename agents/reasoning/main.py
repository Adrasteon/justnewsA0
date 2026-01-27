"""
Reasoning Agent - Simplified Refactored Implementation

This module provides symbolic reasoning, fact validation, contradiction detection,
and explainability for news analysis using the Nucleoid reasoning engine.

Key Features:
- Nucleoid symbolic reasoning engine
- Fact and rule management
- Contradiction detection
- Query execution and validation
- MCP Bus integration
- Enhanced reasoning with news domain rules

All functions include robust error handling, validation, and fallbacks.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from agents.common.mcp_bus_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

# Configure logging
bootstrap_observability("reasoning")
logger = get_logger(__name__)

# Global engine instances
_reasoning_engine: Any | None = None
_enhanced_engine: Any | None = None


def get_reasoning_engine():
    """Get or create the global reasoning engine instance."""
    global _reasoning_engine
    if _reasoning_engine is None:
        from .reasoning_engine import ReasoningConfig, ReasoningEngine

        config = ReasoningConfig()
        _reasoning_engine = ReasoningEngine(config)
    return _reasoning_engine


def get_enhanced_engine():
    """Get or create the global enhanced reasoning engine instance."""
    global _enhanced_engine
    if _enhanced_engine is None:
        from .reasoning_engine import EnhancedReasoningEngine

        base_engine = get_reasoning_engine()
        _enhanced_engine = EnhancedReasoningEngine(base_engine)
    return _enhanced_engine


# Environment variables
REASONING_AGENT_PORT = int(os.environ.get("REASONING_AGENT_PORT", 8008))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


# Pydantic models
class ToolCall(BaseModel):
    """Standard MCP tool call format"""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}


class Fact(BaseModel):
    """Fact data model"""

    data: dict[str, Any]


class Facts(BaseModel):
    """Multiple facts data model"""

    facts: list[dict[str, Any]]


class Rule(BaseModel):
    """Rule data model"""

    rule: str


class Query(BaseModel):
    """Query data model"""

    query: str


class Evaluate(BaseModel):
    """Evaluation data model"""

    expression: str


class ContradictionCheck(BaseModel):
    """Contradiction check data model"""

    statements: list[str]


class FactValidation(BaseModel):
    """Fact validation data model"""

    claim: str
    context: dict[str, Any] | None = None





# FastAPI app setup
app = FastAPI(
    title="JustNews V4 Reasoning Agent (Nucleoid)",
    description="Symbolic reasoning and fact validation for news analysis",
)

metrics = JustNewsMetrics("reasoning")

app.middleware("http")(metrics.request_middleware)


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("🔧 Reasoning agent is starting up...")

    # Initialize engines
    try:
        global _reasoning_engine, _enhanced_engine
        _reasoning_engine = get_reasoning_engine()
        _enhanced_engine = get_enhanced_engine()
        logger.info("✅ Reasoning engines initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize reasoning engines: {e}")
        _reasoning_engine = None
        _enhanced_engine = None

    # MCP Bus registration
    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    mcp_bus_client.register_agent(
        agent_name="reasoning",
        agent_address=f"http://localhost:{REASONING_AGENT_PORT}",
        tools=[
            "add_fact",
            "add_facts",
            "add_rule",
            "query",
            "evaluate",
            "validate_claim",
            "explain_reasoning",
            "pipeline_validate",
        ],
    )

    logger.info("✅ Reasoning agent startup complete")

    yield

    # Shutdown logic
    logger.info("🔧 Reasoning agent is shutting down...")

    # Save state if engines available
    if _reasoning_engine:
        try:
            state_file = os.path.join(os.path.dirname(__file__), "reasoning_state.json")
            state_data = {
                "facts": _reasoning_engine.get_facts(),
                "rules": _reasoning_engine.get_rules(),
                "timestamp": datetime.now().isoformat(),
            }
            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2)
            logger.info(f"💾 Reasoning state saved to {state_file}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save reasoning state: {e}")

    logger.info("✅ Reasoning agent shutdown complete")


app.router.lifespan_context = lifespan


# Utility functions
def log_feedback(event: str, details: dict[str, Any]):
    """Log feedback for debugging and improvement."""
    feedback_log = os.path.join(os.path.dirname(__file__), "feedback_reasoning.log")
    try:
        with open(feedback_log, "a", encoding="utf-8") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"{timestamp}\t{event}\t{json.dumps(details)}\n")
    except Exception as e:
        logger.warning(f"⚠️ Failed to log feedback: {e}")


# API Endpoints


@app.post("/add_fact")
async def add_fact_endpoint(call: ToolCall):
    """Add a fact to the reasoning system."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract fact from args or kwargs
        if call.args:
            fact_data = (
                call.args[0]
                if isinstance(call.args[0], dict)
                else {"statement": str(call.args[0])}
            )
        else:
            fact_data = call.kwargs.get("fact", call.kwargs.get("data", {}))

        result = await engine.add_fact(fact_data)

        # Log feedback
        log_feedback(
            "add_fact", {"fact_data": fact_data, "result": str(result), "success": True}
        )

        return {"success": True, "result": result, "fact_id": len(engine.facts_store)}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "add_fact_error",
            {"fact_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/add_facts")
async def add_facts_endpoint(call: ToolCall):
    """Add multiple facts to the reasoning system."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract facts from args or kwargs
        if call.args and isinstance(call.args[0], list):
            facts_list = call.args[0]
        else:
            facts_list = call.kwargs.get("facts", [])

        results = []
        for fact_data in facts_list:
            if isinstance(fact_data, dict):
                result = await engine.add_fact(fact_data)
                results.append(result)
            else:
                result = await engine.add_fact({"statement": str(fact_data)})
                results.append(result)

        # Log feedback
        log_feedback(
            "add_facts",
            {
                "facts_count": len(facts_list),
                "results": [str(r) for r in results],
                "success": True,
            },
        )

        return {"success": True, "count": len(results), "results": results}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "add_facts_error",
            {"facts_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/add_rule")
async def add_rule_endpoint(call: ToolCall):
    """Add a logical rule to the reasoning system."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract rule from args or kwargs
        if call.args:
            rule = str(call.args[0])
        else:
            rule = call.kwargs.get("rule", "")

        if not rule:
            raise ValueError("Rule cannot be empty")

        result = await engine.add_rule(rule)

        # Log feedback
        log_feedback("add_rule", {"rule": rule, "result": str(result), "success": True})

        return {
            "success": True,
            "result": result,
            "rule_count": len(engine.rules_store),
        }

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "add_rule_error",
            {"rule_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/query")
async def query_endpoint(call: ToolCall):
    """Execute a symbolic reasoning query."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract query from args or kwargs
        if call.args:
            query = str(call.args[0])
        else:
            query = call.kwargs.get("query", "")

        if not query:
            raise ValueError("Query cannot be empty")

        result = await engine.query(query)

        # Log feedback
        log_feedback("query", {"query": query, "result": str(result), "success": True})

        return {"success": True, "result": result, "query": query}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "query_error",
            {"query_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/evaluate")
async def evaluate_endpoint(call: ToolCall):
    """Evaluate contradictions and logical consistency."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract evaluation request
        if call.args and isinstance(call.args[0], list):
            statements = call.args[0]
        elif call.args:
            statements = [str(call.args[0])]
        else:
            statements = call.kwargs.get("statements", [])
            if not statements:
                # Evaluate all current facts and rules
                statements = list(engine.facts_store.values()) + engine.rules_store

        if not statements:
            return {"success": True, "result": "No statements to evaluate"}

        # Convert non-string statements to strings
        str_statements = []
        for stmt in statements:
            if isinstance(stmt, dict):
                if "statement" in stmt:
                    str_statements.append(stmt["statement"])
                else:
                    str_statements.append(json.dumps(stmt))
            else:
                str_statements.append(str(stmt))

        result = await engine.evaluate_contradiction(str_statements)

        # Log feedback
        log_feedback(
            "evaluate",
            {
                "statements_count": len(str_statements),
                "has_contradictions": result.get("has_contradictions", False),
                "contradictions_count": len(result.get("contradictions", [])),
                "success": True,
            },
        )

        return {"success": True, "result": result}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "evaluate_error",
            {
                "evaluation_data": call.args if call.args else call.kwargs,
                "error": error_msg,
            },
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/validate_claim")
async def validate_claim_endpoint(call: ToolCall):
    """Validate a news claim against known facts and rules."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract claim
        if call.args:
            claim = str(call.args[0])
            context = call.args[1] if len(call.args) > 1 else {}
        else:
            claim = call.kwargs.get("claim", "")
            context = call.kwargs.get("context", {})

        if not claim:
            raise ValueError("Claim cannot be empty")

        # Use enhanced engine if available
        enhanced = get_enhanced_engine()
        if enhanced:
            try:
                validation_result = await enhanced.validate_news_claim_with_context(
                    claim, context
                )
            except Exception:
                validation_result = None

        if not enhanced or validation_result is None:
            # Fallback to basic contradiction evaluation
            existing_statements = []
            for fact in engine.facts_store.values():
                if isinstance(fact, dict) and "statement" in fact:
                    existing_statements.append(fact["statement"])
            existing_statements.extend(engine.rules_store)

            test_statements = existing_statements + [claim]
            contradiction_result = await engine.evaluate_contradiction(test_statements)

            validation_result = {
                "claim": claim,
                "context": context,
                "valid": not contradiction_result["has_contradictions"],
                "contradictions": contradiction_result["contradictions"],
                "confidence": 1.0 - (len(contradiction_result["contradictions"]) * 0.2),
            }

        # Log feedback
        log_feedback(
            "validate_claim",
            {
                "claim": claim,
                "valid": validation_result.get("valid", False),
                "contradictions_count": len(
                    validation_result.get("contradictions", [])
                ),
                "confidence": validation_result.get("confidence", 0.0),
            },
        )

        return {"success": True, "result": validation_result}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "validate_claim_error",
            {"claim_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/explain_reasoning")
async def explain_reasoning_endpoint(call: ToolCall):
    """Provide explainable reasoning for a query or validation."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        # Extract query
        if call.args:
            query = str(call.args[0])
        else:
            query = call.kwargs.get("query", "")

        if not query:
            raise ValueError("Query cannot be empty")

        # Execute query and provide explanation
        result = await engine.query(query)

        # Generate explanation
        enhanced = get_enhanced_engine()
        explanation = {
            "query": query,
            "result": result,
            "reasoning_steps": [
                f"1. Executed query: '{query}'",
                f"2. Applied {len(engine.rules_store)} logical rules",
                f"3. Checked against {len(engine.facts_store)} known facts",
                f"4. Result: {result}",
            ],
            "facts_used": list(engine.facts_store.keys()),
            "rules_applied": engine.rules_store,
            "confidence": 0.8 if result else 0.2,
            "enhanced_available": enhanced is not None,
        }

        # Log feedback
        log_feedback(
            "explain_reasoning",
            {"query": query, "result": str(result), "explanation_provided": True},
        )

        return {"success": True, "result": explanation}

    except Exception as e:
        error_msg = str(e)
        log_feedback(
            "explain_reasoning_error",
            {"query_data": call.args if call.args else call.kwargs, "error": error_msg},
        )
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.post("/pipeline/validate")
async def pipeline_validate_endpoint(payload: dict[str, Any]):
    """Run the three-stage pipeline: neural assessment -> reasoning -> integrated decision."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    try:
        assessment = payload.get("assessment", {})
        article_metadata = payload.get("article_metadata", {})

        # Stage 1: Convert neural assessment to statements
        statements = await engine._ingest_neural_assessment(assessment)

        # Temporarily add statements to the engine
        for stmt in statements:
            try:
                await engine.add_fact({"statement": stmt})
            except Exception:
                pass

        # Stage 2: Reasoning validation
        enhanced = get_enhanced_engine()
        if enhanced:
            try:
                logic_res = await enhanced.validate_news_claim_with_context(
                    claim=assessment.get("extracted_claims", [{}])[0]
                    if assessment.get("extracted_claims")
                    else "",
                    article_metadata=article_metadata,
                )
            except Exception:
                logic_res = None
        else:
            logic_res = None

        if logic_res is None:
            # Fallback: aggregate evaluation
            test_statements = list(engine.facts_store.values()) + engine.rules_store
            contradiction_res = await engine.evaluate_contradiction(
                [str(s) for s in test_statements]
            )
            logic_res = {
                "logical_validation": {
                    "consistency_check": "PASS"
                    if not contradiction_res.get("has_contradictions")
                    else "FAIL",
                    "rule_compliance": "UNKNOWN",
                    "temporal_validity": True,
                },
                "orchestration_decision": {
                    "consensus_confidence": assessment.get("confidence", 0.5),
                    "escalation_required": False,
                    "recommended_action": "REVIEW"
                    if contradiction_res.get("has_contradictions")
                    else "APPROVE",
                },
            }

        # Stage 3: Integrated decision
        overall_confidence = (
            float(assessment.get("confidence", 0.5)) * 0.6
            + float(
                logic_res.get("orchestration_decision", {}).get(
                    "consensus_confidence", 0.0
                )
            )
            * 0.4
        )

        final = {
            "version": "1.0",
            "overall_confidence": overall_confidence,
            "verification_status": logic_res.get("orchestration_decision", {}).get(
                "recommended_action", "UNKNOWN"
            ),
            "explanation": logic_res.get("logical_validation", {}),
            "neural_assessment": assessment,
            "logical_validation": logic_res.get("logical_validation", {}),
            "processing_summary": {
                "fact_checker_confidence": assessment.get("confidence", 0.5),
                "reasoning_validation": logic_res.get("orchestration_decision", {}).get(
                    "consensus_confidence", 0.0
                ),
                "final_recommendation": logic_res.get("orchestration_decision", {}).get(
                    "recommended_action", "UNKNOWN"
                ),
            },
        }

        # Log pipeline outcome
        log_feedback(
            "pipeline_run",
            {
                "final_overall_confidence": final["overall_confidence"],
                "verification_status": final["verification_status"],
            },
        )

        return {"success": True, "result": final}

    except Exception as e:
        log_feedback("pipeline_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e)) from e


# Status and health endpoints
@app.get("/facts")
async def get_facts():
    """Retrieve all stored facts."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    return {"facts": engine.get_facts(), "count": len(engine.facts_store)}


@app.get("/rules")
async def get_rules():
    """Retrieve all stored rules."""
    engine = get_reasoning_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not available")

    return {"rules": engine.get_rules(), "count": len(engine.rules_store)}


@app.get("/status")
async def get_status():
    """Get reasoning engine status."""
    engine = get_reasoning_engine()
    if not engine:
        return {
            "status": "unavailable",
            "nucleoid_available": False,
            "facts_count": 0,
            "rules_count": 0,
        }

    return {
        "status": "ok",
        "nucleoid_available": True,
        "facts_count": len(engine.facts_store),
        "rules_count": len(engine.rules_store),
        "enhanced_available": get_enhanced_engine() is not None,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    engine = get_reasoning_engine()
    status = "ok" if engine else "unavailable"
    return {"status": status, "nucleoid_available": engine is not None}


@app.get("/ready")
async def ready():
    """Readiness endpoint."""
    return {"ready": True}


@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")


# MCP Bus integration
@app.post("/call")
async def call_tool(request: dict[str, Any]):
    """MCP bus integration - handles tool calls from other agents."""
    try:
        tool = request.get("tool", "")
        args = request.get("args", [])
        kwargs = request.get("kwargs", {})

        # Create ToolCall object
        call = ToolCall(args=args, kwargs=kwargs)

        # Route to appropriate endpoint
        tool_map = {
            "add_fact": add_fact_endpoint,
            "add_facts": add_facts_endpoint,
            "add_rule": add_rule_endpoint,
            "query": query_endpoint,
            "evaluate": evaluate_endpoint,
            "validate_claim": validate_claim_endpoint,
            "explain_reasoning": explain_reasoning_endpoint,
        }

        if tool in tool_map:
            return await tool_map[tool](call)
        else:
            available_tools = list(tool_map.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tool: {tool}. Available tools: {available_tools}",
            )

    except Exception as e:
        log_feedback("mcp_call_error", {"request": request, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e)) from e


# Main entry point
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("REASONING_AGENT_PORT", 8008))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
