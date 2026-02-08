"""
Reasoning Tools - Utility Functions for Symbolic Reasoning

This module provides utility functions for symbolic reasoning, fact validation,
contradiction detection, and explainability for news analysis.

Key Functions:
- add_fact: Add facts to the reasoning system
- add_rule: Add logical rules
- query: Execute symbolic reasoning queries
- evaluate_contradiction: Detect logical inconsistencies
- validate_claim: Validate news claims
- explain_reasoning: Provide explainable reasoning

All functions include robust error handling, validation, and fallbacks.
"""

import json
from datetime import datetime
from typing import Any

from common.observability import get_logger

# Configure logging
logger = get_logger(__name__)

# Global engine instances
_engine: Any | None = None
_enhanced_engine: Any | None = None


def get_reasoning_engine():
    """Get or create the global reasoning engine instance."""
    global _engine
    if _engine is None:
        from .reasoning_engine import ReasoningConfig, ReasoningEngine

        config = ReasoningConfig()
        _engine = ReasoningEngine(config)
    return _engine


def get_enhanced_engine():
    """Get or create the global enhanced reasoning engine instance."""
    global _enhanced_engine
    if _enhanced_engine is None:
        from .reasoning_engine import EnhancedReasoningEngine

        base_engine = get_reasoning_engine()
        _enhanced_engine = EnhancedReasoningEngine(base_engine)
    return _enhanced_engine


async def process_reasoning_request(operation_type: str, **kwargs) -> dict[str, Any]:
    """
    Process a reasoning request using the reasoning engine.

    Args:
        operation_type: Type of reasoning operation to perform
        **kwargs: Additional parameters for operation

    Returns:
        Reasoning operation results dictionary
    """
    engine = get_reasoning_engine()

    try:
        logger.info(f"🧠 Processing {operation_type} reasoning operation")

        if operation_type == "add_fact":
            result = await engine.add_fact(kwargs.get("fact_data", {}))
        elif operation_type == "add_rule":
            result = await engine.add_rule(kwargs.get("rule", ""))
        elif operation_type == "query":
            result = await engine.query(kwargs.get("query", ""))
        elif operation_type == "evaluate":
            result = await engine.evaluate_contradiction(kwargs.get("statements", []))
        elif operation_type == "validate_claim":
            result = await validate_claim(
                kwargs.get("claim", ""), kwargs.get("context", {})
            )
        elif operation_type == "explain":
            result = await explain_reasoning(kwargs.get("query", ""))
        else:
            result = {"error": f"Unknown operation type: {operation_type}"}

        logger.info(f"✅ {operation_type} reasoning operation completed")
        return result

    except Exception as e:
        logger.error(f"❌ {operation_type} reasoning operation failed: {e}")
        return {"error": str(e)}


async def add_fact(fact_data: dict[str, Any]) -> dict[str, Any]:
    """
    Add a fact to the reasoning system.

    This function adds factual information to the Nucleoid reasoning engine
    for use in symbolic reasoning and validation.

    Args:
        fact_data: Dictionary containing fact information

    Returns:
        Dictionary containing operation result
    """
    if not fact_data:
        return {"error": "Empty fact data provided"}

    try:
        engine = get_reasoning_engine()

        # Add fact to engine
        result = await engine.add_fact(fact_data)

        # Log feedback for training
        engine.log_feedback("add_fact", {"fact_data": fact_data, "result": str(result)})

        return {
            "success": True,
            "result": result,
            "fact_id": len(engine.facts_store),
            "analysis_metadata": {
                "operation": "add_fact",
                "timestamp": datetime.now().isoformat(),
                "analyzer_version": "reasoning_v2_add_fact",
            },
        }

    except Exception as e:
        logger.error(f"Error adding fact: {e}")
        return {"error": str(e)}


async def add_rule(rule: str) -> dict[str, Any]:
    """
    Add a logical rule to the reasoning system.

    This function adds logical rules to the Nucleoid reasoning engine
    for use in symbolic reasoning and validation.

    Args:
        rule: Logical rule string

    Returns:
        Dictionary containing operation result
    """
    if not rule or not rule.strip():
        return {"error": "Empty rule provided"}

    try:
        engine = get_reasoning_engine()

        # Add rule to engine
        result = await engine.add_rule(rule)

        # Log feedback for training
        engine.log_feedback("add_rule", {"rule": rule, "result": str(result)})

        return {
            "success": True,
            "result": result,
            "rule_count": len(engine.rules_store),
            "analysis_metadata": {
                "operation": "add_rule",
                "timestamp": datetime.now().isoformat(),
                "analyzer_version": "reasoning_v2_add_rule",
            },
        }

    except Exception as e:
        logger.error(f"Error adding rule: {e}")
        return {"error": str(e)}


async def query(query_str: str) -> dict[str, Any]:
    """
    Execute a symbolic reasoning query.

    This function executes queries against the Nucleoid reasoning engine
    to retrieve information or perform logical reasoning.

    Args:
        query_str: Query string to execute

    Returns:
        Dictionary containing query result
    """
    if not query_str or not query_str.strip():
        return {"error": "Empty query provided"}

    try:
        engine = get_reasoning_engine()

        # Execute query
        result = await engine.query(query_str)

        # Log feedback for training
        engine.log_feedback("query", {"query": query_str, "result": str(result)})

        return {
            "success": True,
            "result": result,
            "query": query_str,
            "analysis_metadata": {
                "operation": "query",
                "timestamp": datetime.now().isoformat(),
                "analyzer_version": "reasoning_v2_query",
            },
        }

    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return {"error": str(e)}


async def evaluate_contradiction(statements: list[str]) -> dict[str, Any]:
    """
    Evaluate contradictions and logical consistency in statements.

    This function analyzes a list of statements for logical contradictions
    and inconsistencies using the Nucleoid reasoning engine.

    Args:
        statements: List of statements to evaluate

    Returns:
        Dictionary containing contradiction analysis
    """
    if not statements:
        return {"error": "No statements provided for evaluation"}

    try:
        engine = get_reasoning_engine()

        # Evaluate contradictions
        result = await engine.evaluate_contradiction(statements)

        # Log feedback for training
        engine.log_feedback(
            "evaluate_contradiction",
            {
                "statements_count": len(statements),
                "has_contradictions": result.get("has_contradictions", False),
                "contradictions_count": len(result.get("contradictions", [])),
            },
        )

        # Add metadata
        result["analysis_metadata"] = {
            "operation": "evaluate_contradiction",
            "statements_count": len(statements),
            "timestamp": datetime.now().isoformat(),
            "analyzer_version": "reasoning_v2_contradiction",
        }

        return result

    except Exception as e:
        logger.error(f"Error evaluating contradictions: {e}")
        return {"error": str(e)}


async def validate_claim(
    claim: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Validate a news claim against known facts and rules.

    This function validates news claims using symbolic reasoning and
    checks for consistency with established facts and rules.

    Args:
        claim: Claim to validate
        context: Additional context for validation

    Returns:
        Dictionary containing validation result
    """
    if not claim or not claim.strip():
        return {"error": "Empty claim provided"}

    try:
        engine = get_reasoning_engine()

        # Use enhanced engine if available
        enhanced = get_enhanced_engine()
        if enhanced:
            try:
                validation_result = await enhanced.validate_news_claim_with_context(
                    claim, context or {}
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

        # Log feedback for training
        engine.log_feedback(
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

        # Add metadata
        validation_result["analysis_metadata"] = {
            "operation": "validate_claim",
            "timestamp": datetime.now().isoformat(),
            "analyzer_version": "reasoning_v2_validation",
            "enhanced_used": enhanced is not None,
        }

        return validation_result

    except Exception as e:
        logger.error(f"Error validating claim: {e}")
        return {"error": str(e)}


async def explain_reasoning(query: str) -> dict[str, Any]:
    """
    Provide explainable reasoning for a query.

    This function executes a query and provides detailed explanation
    of the reasoning process and results.

    Args:
        query: Query to explain

    Returns:
        Dictionary containing explanation
    """
    if not query or not query.strip():
        return {"error": "Empty query provided"}

    try:
        engine = get_reasoning_engine()

        # Execute query
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

        # Log feedback for training
        engine.log_feedback(
            "explain_reasoning",
            {"query": query, "result": str(result), "explanation_provided": True},
        )

        # Add metadata
        explanation["analysis_metadata"] = {
            "operation": "explain_reasoning",
            "timestamp": datetime.now().isoformat(),
            "analyzer_version": "reasoning_v2_explanation",
        }

        return explanation

    except Exception as e:
        logger.error(f"Error explaining reasoning: {e}")
        return {"error": str(e)}


async def pipeline_validate(
    assessment: dict[str, Any], article_metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Run the three-stage pipeline: neural assessment -> reasoning -> integrated decision.

    This function implements the complete validation pipeline for news analysis.

    Args:
        assessment: Neural assessment data
        article_metadata: Article metadata

    Returns:
        Dictionary containing pipeline validation result
    """
    if not assessment:
        return {"error": "Empty assessment provided"}

    try:
        engine = get_reasoning_engine()

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
                    article_metadata=article_metadata or {},
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

        # Log feedback for training
        engine.log_feedback(
            "pipeline_validate",
            {
                "final_overall_confidence": final["overall_confidence"],
                "verification_status": final["verification_status"],
            },
        )

        # Add metadata
        final["analysis_metadata"] = {
            "operation": "pipeline_validate",
            "timestamp": datetime.now().isoformat(),
            "analyzer_version": "reasoning_v2_pipeline",
        }

        return final

    except Exception as e:
        logger.error(f"Error in pipeline validation: {e}")
        return {"error": str(e)}


# Utility functions
def get_performance_stats() -> dict[str, Any]:
    """Get reasoning engine performance statistics."""
    try:
        engine = get_reasoning_engine()
        return engine.get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return {"error": str(e), "engine_available": False}


def get_model_status() -> dict[str, Any]:
    """Get status of reasoning components."""
    try:
        engine = get_reasoning_engine()
        enhanced = get_enhanced_engine()
        return {
            "engine_available": engine is not None,
            "enhanced_available": enhanced is not None,
            "facts_count": len(engine.facts_store) if engine else 0,
            "rules_count": len(engine.rules_store) if engine else 0,
        }
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return {"error": str(e), "components_available": False}


def log_feedback(feedback_data: dict[str, Any]) -> dict[str, Any]:
    """Log user feedback for model improvement."""
    try:
        engine = get_reasoning_engine()
        return engine.log_feedback(feedback_data)
    except Exception as e:
        logger.error(f"Error logging feedback: {e}")
        return {"error": str(e), "logged": False}


def get_facts() -> dict[str, Any]:
    """Retrieve all stored facts."""
    try:
        engine = get_reasoning_engine()
        return engine.get_facts()
    except Exception as e:
        logger.error(f"Error getting facts: {e}")
        return {"error": str(e), "facts": {}}


def get_rules() -> list[str]:
    """Retrieve all stored rules."""
    try:
        engine = get_reasoning_engine()
        return engine.get_rules()
    except Exception as e:
        logger.error(f"Error getting rules: {e}")
        return []


def clear_knowledge_base() -> dict[str, Any]:
    """Clear all facts and rules from the knowledge base."""
    try:
        engine = get_reasoning_engine()
        return engine.clear()
    except Exception as e:
        logger.error(f"Error clearing knowledge base: {e}")
        return {"error": str(e), "cleared": False}


def get_training_status() -> dict[str, Any]:
    """Get online training status for reasoning models."""
    try:
        engine = get_reasoning_engine()
        return engine.get_training_status()
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return {"error": str(e), "online_training_enabled": False}


async def health_check() -> dict[str, Any]:
    """
    Perform health check on reasoning components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_reasoning_engine()
        enhanced = get_enhanced_engine()

        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {
                "reasoning_engine": "healthy" if engine else "unhealthy",
                "enhanced_engine": "healthy" if enhanced else "degraded",
                "facts_store": "healthy",
                "rules_store": "healthy",
            },
            "facts_count": len(engine.facts_store) if engine else 0,
            "rules_count": len(engine.rules_store) if engine else 0,
        }

        # Check for any unhealthy components
        unhealthy_components = [
            k for k, v in health_status["components"].items() if v == "unhealthy"
        ]
        if unhealthy_components:
            health_status["overall_status"] = "unhealthy"
            health_status["issues"] = [
                f"Component {comp} is unhealthy" for comp in unhealthy_components
            ]

        # Check minimum functionality
        if not engine:
            health_status["overall_status"] = "unhealthy"
            health_status["issues"] = health_status.get("issues", []) + [
                "Reasoning engine not available"
            ]

        logger.info(f"🏥 Reasoning health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Reasoning health check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


def validate_reasoning_result(
    result: dict[str, Any], expected_fields: list[str] | None = None
) -> bool:
    """
    Validate reasoning result structure.

    Args:
        result: Reasoning result to validate
        expected_fields: List of expected fields (optional)

    Returns:
        True if result is valid, False otherwise
    """
    if not isinstance(result, dict):
        return False

    if "error" in result:
        return True  # Error results are valid

    if expected_fields:
        return all(field in result for field in expected_fields)

    # Basic validation for common fields
    common_fields = ["analysis_metadata", "timestamp"]
    return any(field in result for field in common_fields)


def format_reasoning_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format reasoning result for output.

    Args:
        result: Reasoning result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            if "error" in result:
                return f"Error: {result['error']}"

            lines = []
            if "success" in result and result["success"]:
                lines.append("Reasoning Operation: SUCCESS")
            else:
                lines.append("Reasoning Operation: FAILED")

            if "result" in result:
                lines.append(f"Result: {result['result']}")

            if "confidence" in result:
                lines.append(f"Confidence: {result['confidence']:.2f}")

            if "facts_count" in result:
                lines.append(f"Facts Count: {result['facts_count']}")

            if "rules_count" in result:
                lines.append(f"Rules Count: {result['rules_count']}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Reasoning Error\n\n{result['error']}"

            lines = ["# Reasoning Results\n"]

            if "success" in result and result["success"]:
                lines.append("## Status: ✅ SUCCESS")
            else:
                lines.append("## Status: ❌ FAILED")

            if "result" in result:
                lines.append(f"## Result\n{result['result']}")

            if "confidence" in result:
                lines.append(f"## Confidence\n{result['confidence']:.2f}")

            if "facts_count" in result:
                lines.append(f"## Knowledge Base\n- Facts: {result['facts_count']}")

            if "rules_count" in result:
                lines.append(f"- Rules: {result['rules_count']}")

            if "reasoning_steps" in result:
                lines.append("## Reasoning Steps")
                for step in result["reasoning_steps"]:
                    lines.append(f"- {step}")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


# Export main functions
__all__ = [
    "add_fact",
    "add_rule",
    "query",
    "evaluate_contradiction",
    "validate_claim",
    "explain_reasoning",
    "pipeline_validate",
    "get_performance_stats",
    "get_model_status",
    "log_feedback",
    "get_facts",
    "get_rules",
    "clear_knowledge_base",
    "get_training_status",
    "health_check",
    "validate_reasoning_result",
    "format_reasoning_output",
    "get_reasoning_engine",
    "get_enhanced_engine",
]
