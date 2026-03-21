"""
Critic Tools - Utility Functions for Content Analysis and Critique

This module provides utility functions for editorial critique and content analysis,
focusing on argument structure, consistency, logical fallacies, and credibility assessment.

Key Functions:
- critique_synthesis: Comprehensive content critique using all analysis tools
- critique_neutrality: Analyze content neutrality and bias indicators
- analyze_argument_structure: Evaluate logical structure of arguments
- assess_editorial_consistency: Check editorial coherence and internal consistency
- detect_logical_fallacies: Identify logical errors and reasoning flaws
- assess_source_credibility: Evaluate evidence quality and sourcing

All functions include robust error handling, validation, and fallbacks.
"""

import json
import re
import statistics
from datetime import datetime
from typing import Any

from common.observability import get_logger

# Configure logging
logger = get_logger(__name__)

# Global engine instance
_engine: Any | None = None


def get_critic_engine():
    """Get or create the global critic engine instance."""
    global _engine
    if _engine is None:
        from .critic_engine import CriticConfig, CriticEngine

        config = CriticConfig()
        _engine = CriticEngine(config)
    return _engine


async def process_critique_request(
    content: str, operation_type: str, **kwargs
) -> dict[str, Any]:
    """
    Process a critique request using the critic engine.

    Args:
        content: Content to critique
        operation_type: Type of critique operation to perform
        **kwargs: Additional parameters for operation

    Returns:
        Critique operation results dictionary
    """
    engine = get_critic_engine()

    try:
        logger.info(
            f"🔍 Processing {operation_type} critique operation for {len(content)} characters"
        )

        if operation_type == "synthesis":
            result = engine.critique_synthesis(content, kwargs.get("url"))
        elif operation_type == "neutrality":
            result = engine.critique_neutrality(content, kwargs.get("url"))
        elif operation_type == "argument":
            result = engine.analyze_argument_structure(content, kwargs.get("url"))
        elif operation_type == "consistency":
            result = engine.assess_editorial_consistency(content, kwargs.get("url"))
        elif operation_type == "fallacies":
            result = engine.detect_logical_fallacies(content, kwargs.get("url"))
        elif operation_type == "credibility":
            result = engine.assess_source_credibility(content, kwargs.get("url"))
        else:
            result = {"error": f"Unknown operation type: {operation_type}"}

        logger.info(f"✅ {operation_type.capitalize()} critique operation completed")

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type=operation_type,
                input_text=content[:5000] if content else "",
                prediction=result,
                confidence=result.get("confidence", 1.0) if isinstance(result, dict) else 1.0,
                source_url=kwargs.get("url", ""),
            )
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to collect training data for {operation_type}: {e}")

        return result

    except Exception as e:
        logger.error(f"❌ {operation_type} critique operation failed: {e}")
        return {"error": str(e)}


def critique_synthesis(content: str, url: str | None = None) -> dict[str, Any]:
    """
    Synthesize comprehensive content critique using all available analysis tools.

    This function provides a complete editorial assessment including argument structure,
    consistency, logical fallacies, and source credibility analysis.

    Args:
        content: Content to critique
        url: Source URL for context

    Returns:
        Dictionary containing comprehensive critique analysis
    """
    if not content or not content.strip():
        return {
            "critique_score": 0.0,
            "assessment": "empty",
            "error": "Empty content provided",
        }

    try:
        engine = get_critic_engine()

        # Perform all analyses
        argument_analysis = engine.analyze_argument_structure(content, url)
        consistency_analysis = engine.assess_editorial_consistency(content, url)
        fallacy_analysis = engine.detect_logical_fallacies(content, url)
        credibility_analysis = engine.assess_source_credibility(content, url)

        # Calculate overall critique score
        critique_score = _calculate_overall_critique_score(
            argument_analysis,
            consistency_analysis,
            fallacy_analysis,
            credibility_analysis,
        )

        # Generate critique summary
        critique_summary = _generate_critique_summary(
            critique_score,
            argument_analysis,
            consistency_analysis,
            fallacy_analysis,
            credibility_analysis,
        )

        result = {
            "critique_score": critique_score,
            "critique_summary": critique_summary,
            "detailed_analysis": {
                "argument_structure": argument_analysis,
                "editorial_consistency": consistency_analysis,
                "logical_fallacies": fallacy_analysis,
                "source_credibility": credibility_analysis,
            },
            "recommendations": _generate_critique_recommendations(
                critique_score,
                argument_analysis,
                consistency_analysis,
                fallacy_analysis,
                credibility_analysis,
            ),
            "analysis_metadata": {
                "content_length": len(content),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_synthesis",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "critique_synthesis",
            {"critique_score": critique_score, "content_length": len(content)},
        )

        return result

    except Exception as e:
        logger.error(f"Error in critique synthesis: {e}")
        return {"error": str(e)}


def critique_neutrality(content: str, url: str | None = None) -> dict[str, Any]:
    """
    Analyze content neutrality and bias indicators.

    This function evaluates content for neutrality, bias indicators, language objectivity,
    and perspective balance to ensure fair and balanced reporting.

    Args:
        content: Content to analyze for neutrality
        url: Source URL for context

    Returns:
        Dictionary containing neutrality analysis
    """
    if not content or not content.strip():
        return {
            "neutrality_score": 0.0,
            "assessment": "empty",
            "error": "Empty content provided",
        }

    try:
        engine = get_critic_engine()

        # Detect bias indicators
        bias_indicators = _detect_bias_indicators(content)

        # Calculate neutrality score
        neutrality_score = _calculate_neutrality_score(content, bias_indicators)

        # Analyze language objectivity
        objectivity_analysis = _analyze_language_objectivity(content)

        # Analyze perspective balance
        perspective_balance = _analyze_perspective_balance(content)

        assessment = {
            "neutrality_score": neutrality_score,
            "bias_indicators": bias_indicators,
            "objectivity_analysis": objectivity_analysis,
            "perspective_balance": perspective_balance,
            "overall_assessment": _generate_neutrality_assessment(
                neutrality_score, bias_indicators
            ),
            "recommendations": _generate_neutrality_recommendations(
                neutrality_score, bias_indicators
            ),
            "analysis_metadata": {
                "content_length": len(content),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_neutrality",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "critique_neutrality",
            {"neutrality_score": neutrality_score, "bias_count": len(bias_indicators)},
        )

        return assessment

    except Exception as e:
        logger.error(f"Error in neutrality analysis: {e}")
        return {"error": str(e)}


def analyze_argument_structure(text: str, url: str | None = None) -> dict[str, Any]:
    """
    Analyze the logical structure of arguments in text content.

    This function evaluates premises, conclusions, logical flow, and argument strength
    to assess the quality of reasoning and argumentation.

    Args:
        text: Content to analyze for argument structure
        url: Source URL for context

    Returns:
        Dictionary containing argument analysis results
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for argument analysis"}

    try:
        engine = get_critic_engine()

        # Extract logical components
        premises = _extract_premises(text)
        conclusions = _extract_conclusions(text)
        logical_flow = _analyze_logical_flow(text)
        argument_strength = _assess_argument_strength(text, premises, conclusions)

        analysis = {
            "premises": premises,
            "conclusions": conclusions,
            "logical_flow": logical_flow,
            "argument_strength": argument_strength,
            "structural_analysis": {
                "premise_conclusion_ratio": len(premises) / max(len(conclusions), 1),
                "logical_connectors_count": len(logical_flow.get("connectors", [])),
                "argument_complexity": _calculate_argument_complexity(
                    premises, conclusions
                ),
                "coherence_score": _calculate_coherence_score(text),
            },
            "analysis_metadata": {
                "text_length": len(text),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_argument_structure",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "analyze_argument_structure",
            {
                "premises_count": len(premises),
                "conclusions_count": len(conclusions),
                "strength_score": argument_strength.get("strength_score", 0.0),
            },
        )

        return analysis

    except Exception as e:
        logger.error(f"Error in argument structure analysis: {e}")
        return {"error": str(e)}


def assess_editorial_consistency(text: str, url: str | None = None) -> dict[str, Any]:
    """
    Assess editorial consistency and internal coherence.

    This function checks for contradictions, coherence, and internal consistency
    within the content to ensure editorial quality.

    Args:
        text: Content to assess for consistency
        url: Source URL for context

    Returns:
        Dictionary containing consistency analysis results
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for consistency assessment"}

    try:
        engine = get_critic_engine()

        contradictions = _detect_contradictions(text)
        coherence_score = _calculate_coherence_score(text)

        result = {
            "contradictions": contradictions,
            "coherence_score": coherence_score,
            "consistency_score": max(0.0, 1.0 - len(contradictions) * 0.2),
            "analysis_metadata": {
                "text_length": len(text),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_consistency",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "assess_editorial_consistency",
            {
                "contradictions_count": len(contradictions),
                "coherence_score": coherence_score,
            },
        )

        return result

    except Exception as e:
        logger.error(f"Error in editorial consistency assessment: {e}")
        return {"error": str(e)}


def detect_logical_fallacies(text: str, url: str | None = None) -> dict[str, Any]:
    """
    Detect logical fallacies and reasoning errors.

    This function identifies common logical fallacies and reasoning flaws
    that may undermine the credibility of the content.

    Args:
        text: Content to analyze for logical fallacies
        url: Source URL for context

    Returns:
        Dictionary containing fallacy detection results
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for fallacy detection"}

    try:
        engine = get_critic_engine()

        fallacies = _detect_common_fallacies(text)

        result = {
            "fallacies_detected": fallacies,
            "fallacy_count": len(fallacies),
            "logical_strength": max(0.0, 1.0 - len(fallacies) * 0.3),
            "analysis_metadata": {
                "text_length": len(text),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_fallacy_detection",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "detect_logical_fallacies",
            {
                "fallacy_count": len(fallacies),
                "logical_strength": result["logical_strength"],
            },
        )

        return result

    except Exception as e:
        logger.error(f"Error in logical fallacy detection: {e}")
        return {"error": str(e)}


def assess_source_credibility(text: str, url: str | None = None) -> dict[str, Any]:
    """
    Assess source credibility and evidence quality.

    This function evaluates the quality and credibility of sources and evidence
    cited within the content.

    Args:
        text: Content to assess for source credibility
        url: Source URL for context

    Returns:
        Dictionary containing credibility assessment results
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for credibility assessment"}

    try:
        engine = get_critic_engine()

        citations = _extract_citations(text)

        result = {
            "citations": citations,
            "citation_count": len(citations),
            "credibility_score": min(1.0, len(citations) * 0.2),
            "analysis_metadata": {
                "text_length": len(text),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_credibility",
            },
        }

        # Log feedback for training
        engine.log_feedback(
            "assess_source_credibility",
            {
                "citation_count": len(citations),
                "credibility_score": result["credibility_score"],
            },
        )

        return result

    except Exception as e:
        logger.error(f"Error in source credibility assessment: {e}")
        return {"error": str(e)}


async def health_check() -> dict[str, Any]:
    """
    Perform health check on critic components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_critic_engine()

        model_status = engine.get_model_status()

        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "mcp_bus": "healthy",  # Assume healthy unless proven otherwise
                "analysis_tools": "healthy",
            },
            "model_status": model_status,
            "processing_stats": getattr(engine, "processing_stats", {}),
        }

        # Check for any unhealthy components
        unhealthy_components = [
            k for k, v in health_status["components"].items() if v == "unhealthy"
        ]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [
                f"Component {comp} is unhealthy" for comp in unhealthy_components
            ]

        # Check model availability
        loaded_models = sum(1 for status in model_status.values() if status is True)
        if loaded_models < 2:  # Require at least 2 of 5 models for basic functionality
            health_status["overall_status"] = "degraded"
            health_status["issues"] = health_status.get("issues", []) + [
                f"Only {loaded_models}/5 AI models loaded"
            ]

        logger.info(f"🏥 Critic health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Critic health check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


def validate_critique_result(
    result: dict[str, Any], expected_fields: list[str] | None = None
) -> bool:
    """
    Validate critique result structure.

    Args:
        result: Critique result to validate
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
    common_fields = ["analysis_metadata", "analysis_timestamp"]
    return any(field in result for field in common_fields)


def format_critique_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format critique result for output.

    Args:
        result: Critique result to format
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
            if "critique_score" in result:
                lines.append(f"Critique Score: {result['critique_score']:.1f}/10")
                lines.append(f"Summary: {result.get('critique_summary', 'N/A')}")

            if "neutrality_score" in result:
                lines.append(f"Neutrality Score: {result['neutrality_score']:.1f}/10")
                lines.append(f"Assessment: {result.get('overall_assessment', 'N/A')}")

            if "argument_strength" in result:
                strength = result["argument_strength"].get("strength_score", 0.0)
                lines.append(f"Argument Strength: {strength:.2f}")

            if "consistency_score" in result:
                lines.append(f"Consistency Score: {result['consistency_score']:.2f}")

            if "fallacy_count" in result:
                lines.append(f"Logical Fallacies: {result['fallacy_count']}")

            if "credibility_score" in result:
                lines.append(f"Source Credibility: {result['credibility_score']:.2f}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Critique Analysis Error\n\n{result['error']}"

            lines = ["# Critique Analysis Results\n"]

            if "critique_score" in result:
                lines.append("## Overall Critique")
                lines.append(f"- **Score**: {result['critique_score']:.1f}/10")
                lines.append(f"- **Summary**: {result.get('critique_summary', 'N/A')}")

            if "neutrality_score" in result:
                lines.append("## Neutrality Analysis")
                lines.append(f"- **Score**: {result['neutrality_score']:.1f}/10")
                lines.append(
                    f"- **Assessment**: {result.get('overall_assessment', 'N/A')}"
                )
                if "bias_indicators" in result and result["bias_indicators"]:
                    lines.append(
                        f"- **Bias Indicators**: {len(result['bias_indicators'])} found"
                    )

            if "argument_strength" in result:
                strength = result["argument_strength"].get("strength_score", 0.0)
                lines.append("## Argument Structure")
                lines.append(f"- **Strength Score**: {strength:.2f}")
                if "premises" in result:
                    lines.append(f"- **Premises**: {len(result['premises'])}")
                if "conclusions" in result:
                    lines.append(f"- **Conclusions**: {len(result['conclusions'])}")

            if "consistency_score" in result:
                lines.append("## Editorial Consistency")
                lines.append(f"- **Score**: {result['consistency_score']:.2f}")
                if "contradictions" in result and result["contradictions"]:
                    lines.append(
                        f"- **Contradictions**: {len(result['contradictions'])} found"
                    )

            if "fallacy_count" in result:
                lines.append("## Logical Analysis")
                lines.append(f"- **Fallacies Detected**: {result['fallacy_count']}")
                lines.append(
                    f"- **Logical Strength**: {result.get('logical_strength', 0.0):.2f}"
                )

            if "credibility_score" in result:
                lines.append("## Source Credibility")
                lines.append(f"- **Score**: {result['credibility_score']:.2f}")
                lines.append(f"- **Citations**: {result.get('citation_count', 0)}")

            if "recommendations" in result and result["recommendations"]:
                lines.append("## Recommendations")
                for rec in result["recommendations"][:5]:
                    lines.append(f"- {rec}")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


# Helper functions (extracted from original tools.py)
def _extract_premises(text: str) -> list[dict[str, Any]]:
    """Extract premises from argument text."""
    premise_indicators = ["because", "since", "given that", "as", "due to"]
    premises = []
    sentences = re.split(r"[.!?]+", text)

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        for indicator in premise_indicators:
            if indicator in sentence.lower():
                premises.append(
                    {
                        "text": sentence,
                        "indicator": indicator,
                        "position": i,
                        "strength": 0.7,
                    }
                )
                break
    return premises


def _extract_conclusions(text: str) -> list[dict[str, Any]]:
    """Extract conclusions from argument text."""
    conclusion_indicators = ["therefore", "thus", "hence", "so", "consequently"]
    conclusions = []
    sentences = re.split(r"[.!?]+", text)

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        for indicator in conclusion_indicators:
            if indicator in sentence.lower():
                conclusions.append(
                    {
                        "text": sentence,
                        "indicator": indicator,
                        "position": i,
                        "strength": 0.7,
                    }
                )
                break
    return conclusions


def _analyze_logical_flow(text: str) -> dict[str, Any]:
    """Analyze logical flow and connectors."""
    connectors = ["however", "but", "furthermore", "moreover", "additionally"]
    found_connectors = []

    for connector in connectors:
        if connector in text.lower():
            found_connectors.append({"connector": connector, "type": "transition"})

    return {
        "connectors": found_connectors,
        "flow_coherence": min(1.0, len(found_connectors) / 3.0),
    }


def _assess_argument_strength(
    text: str, premises: list[dict], conclusions: list[dict]
) -> dict[str, Any]:
    """Assess overall argument strength."""
    if not premises and not conclusions:
        return {"strength_score": 0.0, "assessment": "No clear argumentative structure"}

    premise_count = len(premises)
    conclusion_count = len(conclusions)
    balance_score = 1.0 - abs(premise_count - conclusion_count) / max(
        premise_count + conclusion_count, 1
    )

    return {
        "strength_score": balance_score,
        "premise_quality": 0.7,
        "conclusion_quality": 0.7,
        "balance_score": balance_score,
        "assessment": "Moderate argumentative structure",
    }


def _calculate_argument_complexity(
    premises: list[dict], conclusions: list[dict]
) -> float:
    """Calculate argument complexity score."""
    return min((len(premises) + len(conclusions)) / 2.0, 10.0)


def _calculate_coherence_score(text: str) -> float:
    """Calculate text coherence."""
    sentences = re.split(r"[.!?]+", text)
    valid_sentences = [s.strip() for s in sentences if s.strip()]

    if len(valid_sentences) < 2:
        return 0.5

    # Simple coherence based on sentence length consistency
    sentence_lengths = [len(s.split()) for s in valid_sentences]
    if len(sentence_lengths) > 1:
        avg_length = statistics.mean(sentence_lengths)
        variation = (
            statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0
        )
        coherence = 1.0 - min(variation / avg_length, 1.0)
    else:
        coherence = 1.0

    return coherence


def _detect_contradictions(text: str) -> list[dict[str, Any]]:
    """Detect internal contradictions."""
    contradictions = []
    sentences = re.split(r"[.!?]+", text)

    # Simple contradiction detection
    for i, sentence1 in enumerate(sentences):
        for _j, sentence2 in enumerate(sentences[i + 1 :], i + 1):
            if "not" in sentence1.lower() and any(
                word in sentence2.lower()
                for word in sentence1.lower().split()
                if word != "not"
            ):
                contradictions.append(
                    {
                        "sentence1": sentence1.strip(),
                        "sentence2": sentence2.strip(),
                        "confidence": 0.5,
                    }
                )

    return contradictions[:3]  # Limit to top 3


def _detect_common_fallacies(text: str) -> list[dict[str, Any]]:
    """Detect common logical fallacies."""
    fallacies = []

    # Ad hominem detection
    if any(
        phrase in text.lower()
        for phrase in ["attacks", "character assassination", "personally"]
    ):
        fallacies.append(
            {
                "fallacy": "ad_hominem",
                "confidence": 0.6,
                "description": "Personal attack rather than addressing argument",
            }
        )

    # Appeal to authority
    if any(
        phrase in text.lower()
        for phrase in ["expert says", "authority claims", "because someone said"]
    ):
        fallacies.append(
            {
                "fallacy": "appeal_to_authority",
                "confidence": 0.5,
                "description": "Inappropriate appeal to authority",
            }
        )

    return fallacies


def _extract_citations(text: str) -> list[dict[str, Any]]:
    """Extract citations and references."""
    citations = []

    # Look for citation patterns
    patterns = [
        (r"according to ([A-Z][a-z]+ [A-Z][a-z]+)", "person"),
        (r"([A-Z][a-z]+ [A-Z][a-z]+) said", "person"),
        (r"study by ([A-Z][A-Za-z\s]+)", "study"),
    ]

    for pattern, citation_type in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            citations.append(
                {
                    "text": match.group(1),
                    "type": citation_type,
                    "position": match.start(),
                }
            )

    return citations


def _calculate_overall_critique_score(
    argument_analysis, consistency_analysis, fallacy_analysis, credibility_analysis
) -> float:
    """Calculate overall critique score from individual analyses"""
    try:
        # Extract scores from each analysis (0-1 scale, convert to 0-10)
        argument_score = (
            argument_analysis.get("argument_strength", {}).get("strength_score", 0.5)
            * 10
        )
        consistency_score = consistency_analysis.get("consistency_score", 0.5) * 10
        fallacy_score = (
            1.0 - fallacy_analysis.get("fallacy_count", 0) * 0.3
        ) * 10  # Invert fallacy count
        credibility_score = credibility_analysis.get("credibility_score", 0.5) * 10

        # Weighted average (argument structure most important)
        weights = {
            "argument": 0.4,
            "consistency": 0.3,
            "fallacy": 0.2,
            "credibility": 0.1,
        }

        overall_score = (
            argument_score * weights["argument"]
            + consistency_score * weights["consistency"]
            + fallacy_score * weights["fallacy"]
            + credibility_score * weights["credibility"]
        )

        return max(0.0, min(10.0, overall_score))

    except Exception:
        return 5.0  # Neutral score on error


def _generate_critique_summary(
    critique_score: float,
    argument_analysis,
    consistency_analysis,
    fallacy_analysis,
    credibility_analysis,
) -> str:
    """Generate human-readable critique summary"""
    try:
        score_level = (
            "excellent"
            if critique_score >= 8.0
            else "good"
            if critique_score >= 6.0
            else "adequate"
            if critique_score >= 4.0
            else "poor"
            if critique_score >= 2.0
            else "very poor"
        )

        summary_parts = [
            f"Overall quality assessment: {score_level} ({critique_score:.1f}/10)"
        ]

        # Add key findings
        if (
            argument_analysis.get("argument_strength", {}).get("strength_score", 0.5)
            < 0.6
        ):
            summary_parts.append("Weak argumentative structure detected")

        if consistency_analysis.get("consistency_score", 0.5) < 0.6:
            contradictions = consistency_analysis.get("contradictions", [])
            summary_parts.append(
                f"Editorial inconsistencies found ({len(contradictions)} issues)"
            )

        fallacy_count = fallacy_analysis.get("fallacy_count", 0)
        if fallacy_count > 0:
            summary_parts.append(
                f"Logical fallacies detected ({fallacy_count} instances)"
            )

        if credibility_analysis.get("credibility_score", 0.5) < 0.6:
            summary_parts.append("Limited source credibility indicators")

        return ". ".join(summary_parts)

    except Exception:
        return f"Critique analysis completed with score {critique_score:.1f}/10"


def _generate_critique_recommendations(
    critique_score: float,
    argument_analysis,
    consistency_analysis,
    fallacy_analysis,
    credibility_analysis,
) -> list[str]:
    """Generate improvement recommendations based on analysis"""
    recommendations = []

    try:
        # Argument structure recommendations
        if (
            argument_analysis.get("argument_strength", {}).get("strength_score", 0.5)
            < 0.6
        ):
            recommendations.append(
                "Strengthen argumentative structure with clearer premises and conclusions"
            )

        # Consistency recommendations
        if consistency_analysis.get("consistency_score", 0.5) < 0.6:
            recommendations.append("Review and resolve editorial inconsistencies")

        # Fallacy recommendations
        fallacy_count = fallacy_analysis.get("fallacy_count", 0)
        if fallacy_count > 0:
            recommendations.append(
                "Address logical fallacies and improve reasoning quality"
            )

        # Credibility recommendations
        if credibility_analysis.get("credibility_score", 0.5) < 0.6:
            recommendations.append(
                "Enhance source credibility with additional citations and references"
            )

        # Overall quality recommendations
        if critique_score < 4.0:
            recommendations.append(
                "Major revision recommended - content requires significant improvement"
            )
        elif critique_score < 6.0:
            recommendations.append(
                "Moderate improvements needed for publication readiness"
            )
        elif critique_score < 8.0:
            recommendations.append("Minor polishing recommended for optimal quality")
        else:
            recommendations.append("Content meets high-quality standards")

        return recommendations[:5]  # Limit to top 5 recommendations

    except Exception:
        return ["Manual review recommended due to analysis error"]


def _detect_bias_indicators(content: str) -> list[dict[str, Any]]:
    """Detect potential bias indicators in content"""
    bias_indicators = []
    content_lower = content.lower()

    # Political bias indicators
    political_terms = {
        "left": ["liberal", "progressive", "democrat", "left-wing"],
        "right": ["conservative", "republican", "right-wing", "traditional"],
        "neutral": ["bipartisan", "centrist", "moderate", "balanced"],
    }

    for bias_type, terms in political_terms.items():
        for term in terms:
            if term in content_lower:
                bias_indicators.append(
                    {
                        "type": "political",
                        "bias_direction": bias_type,
                        "indicator": term,
                        "context": _get_word_context(content, term),
                        "strength": 0.6,
                    }
                )

    # Sensationalism indicators
    sensational_terms = [
        "shocking",
        "outrageous",
        "unbelievable",
        "scandal",
        "crisis",
        "disaster",
    ]
    for term in sensational_terms:
        if term in content_lower:
            bias_indicators.append(
                {
                    "type": "sensationalism",
                    "indicator": term,
                    "context": _get_word_context(content, term),
                    "strength": 0.4,
                }
            )

    # Loaded language indicators
    loaded_terms = [
        "obviously",
        "clearly",
        "undoubtedly",
        "of course",
        "everyone knows",
    ]
    for term in loaded_terms:
        if term in content_lower:
            bias_indicators.append(
                {
                    "type": "loaded_language",
                    "indicator": term,
                    "context": _get_word_context(content, term),
                    "strength": 0.5,
                }
            )

    return bias_indicators


def _calculate_neutrality_score(content: str, bias_indicators: list[dict]) -> float:
    """Calculate overall neutrality score"""
    try:
        base_score = 8.0  # Start with high neutrality assumption

        # Reduce score based on bias indicators
        for indicator in bias_indicators:
            base_score -= indicator.get("strength", 0.5)

        # Reduce score for imbalanced perspective
        perspective_score = _analyze_perspective_balance(content).get(
            "balance_score", 0.5
        )
        base_score = base_score * 0.7 + perspective_score * 10 * 0.3

        # Reduce score for lack of source attribution
        attribution_score = _assess_source_attribution(content)
        base_score = base_score * 0.8 + attribution_score * 10 * 0.2

        return max(0.0, min(10.0, base_score))

    except Exception:
        return 5.0


def _analyze_language_objectivity(content: str) -> dict[str, Any]:
    """Analyze language objectivity indicators"""
    try:
        # Count objective vs subjective language
        objective_indicators = [
            "according to",
            "research shows",
            "data indicates",
            "study finds",
        ]
        subjective_indicators = [
            "i believe",
            "in my opinion",
            "i think",
            "clearly",
            "obviously",
        ]

        objective_count = sum(
            1 for ind in objective_indicators if ind in content.lower()
        )
        subjective_count = sum(
            1 for ind in subjective_indicators if ind in content.lower()
        )

        objectivity_ratio = objective_count / max(1, objective_count + subjective_count)

        return {
            "objective_indicators": objective_count,
            "subjective_indicators": subjective_count,
            "objectivity_ratio": objectivity_ratio,
            "objectivity_score": objectivity_ratio * 10,
        }

    except Exception:
        return {"objectivity_score": 5.0}


def _analyze_perspective_balance(content: str) -> dict[str, Any]:
    """Analyze balance of different perspectives"""
    try:
        # Simple heuristic: look for counter-arguments or alternative views
        balance_indicators = [
            "however",
            "on the other hand",
            "alternatively",
            "critics argue",
            "supporters say",
        ]
        balance_count = sum(1 for ind in balance_indicators if ind in content.lower())

        # Assess quote balance
        quote_count = content.count('"')
        balance_score = min(1.0, (balance_count * 0.3 + quote_count * 0.1))

        return {
            "balance_indicators": balance_count,
            "quote_count": quote_count,
            "balance_score": balance_score,
        }

    except Exception:
        return {"balance_score": 0.5}


def _assess_source_attribution(content: str) -> float:
    """Assess quality of source attribution"""
    try:
        attribution_indicators = ["according to", "cited by", "source:", "reference:"]
        attribution_count = sum(
            1 for ind in attribution_indicators if ind in content.lower()
        )

        # Normalize to 0-1 scale
        return min(1.0, attribution_count / 3.0)

    except Exception:
        return 0.5


def _generate_neutrality_assessment(
    neutrality_score: float, bias_indicators: list[dict]
) -> str:
    """Generate neutrality assessment summary"""
    try:
        if neutrality_score >= 8.0:
            assessment = "Highly neutral and balanced content"
        elif neutrality_score >= 6.0:
            assessment = "Generally neutral with minor bias indicators"
        elif neutrality_score >= 4.0:
            assessment = "Moderate neutrality concerns requiring attention"
        else:
            assessment = "Significant neutrality issues detected"

        if bias_indicators:
            assessment += f" ({len(bias_indicators)} bias indicators found)"

        return assessment

    except Exception:
        return "Neutrality assessment completed"


def _generate_neutrality_recommendations(
    neutrality_score: float, bias_indicators: list[dict]
) -> list[str]:
    """Generate neutrality improvement recommendations"""
    recommendations = []

    try:
        if neutrality_score < 6.0:
            recommendations.append(
                "Review content for potential bias and ensure balanced perspective"
            )

        if any(ind["type"] == "political" for ind in bias_indicators):
            recommendations.append(
                "Balance political perspectives and avoid partisan language"
            )

        if any(ind["type"] == "sensationalism" for ind in bias_indicators):
            recommendations.append(
                "Tone down sensational language for more objective reporting"
            )

        if neutrality_score < 4.0:
            recommendations.append(
                "Major revision needed - content shows significant bias"
            )

        if not recommendations:
            recommendations.append("Content maintains good neutrality standards")

        return recommendations

    except Exception:
        return ["Manual neutrality review recommended"]


def _get_word_context(text: str, word: str, context_chars: int = 50) -> str:
    """Get context around a word in text"""
    try:
        word_lower = word.lower()
        text_lower = text.lower()
        start_idx = text_lower.find(word_lower)

        if start_idx == -1:
            return ""

        start = max(0, start_idx - context_chars)
        end = min(len(text), start_idx + len(word) + context_chars)

        context = text[start:end]
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    except Exception:
        return ""


def evaluate_traceability_balance(
    analysis_report: dict[str, Any],
    *,
    min_distinct_sides: int = 2,
    disputed_topic_hard_gate: bool = False,
    allow_opinion_as_factual_corroboration: bool = False,
) -> dict[str, Any]:
    """Evaluate perspective and attribution coverage from structured traceability payloads."""
    statements = analysis_report.get("attributed_statements") or []
    quotes = analysis_report.get("attributed_quotes") or []

    attributed_statement_count = sum(
        1
        for item in statements
        if isinstance(item, dict) and (item.get("speaker_entity_id") or item.get("speaker_name") or item.get("attribution_text"))
    )
    attributed_quote_count = sum(
        1
        for item in quotes
        if isinstance(item, dict) and (item.get("speaker_entity_id") or item.get("speaker_name") or item.get("attribution_text"))
    )

    side_labels = {
        str(item.get("perspective_label") or "unknown").strip().lower()
        for item in statements
        if isinstance(item, dict)
    }
    side_labels.discard("")

    opinion_items = [
        item for item in statements if isinstance(item, dict) and bool(item.get("is_opinion"))
    ]
    factual_items = [
        item
        for item in statements + quotes
        if isinstance(item, dict)
        and bool(item.get("counts_as_factual_corroboration"))
    ]

    if not allow_opinion_as_factual_corroboration:
        factual_items = [
            item
            for item in factual_items
            if not bool(item.get("is_opinion", False))
        ]

    missing_reasons: list[str] = []
    if len(side_labels) < min_distinct_sides:
        missing_reasons.append("insufficient_distinct_sides")
    if attributed_statement_count + attributed_quote_count == 0:
        missing_reasons.append("missing_attribution")
    if len(factual_items) == 0:
        missing_reasons.append("missing_factual_corroboration")

    gate_result = "pass"
    if missing_reasons and disputed_topic_hard_gate:
        gate_result = "fail"
    elif missing_reasons:
        gate_result = "warning"

    return {
        "gate_result": gate_result,
        "missing_reasons": missing_reasons,
        "metrics": {
            "distinct_sides_found": len(side_labels),
            "min_distinct_sides": int(min_distinct_sides),
            "attributed_statement_count": attributed_statement_count,
            "attributed_quote_count": attributed_quote_count,
            "opinion_items_count": len(opinion_items),
            "factual_items_count": len(factual_items),
        },
        "policy": {
            "disputed_topic_hard_gate": disputed_topic_hard_gate,
            "allow_opinion_as_factual_corroboration": allow_opinion_as_factual_corroboration,
        },
    }


# Export main functions
__all__ = [
    "critique_synthesis",
    "critique_neutrality",
    "analyze_argument_structure",
    "assess_editorial_consistency",
    "detect_logical_fallacies",
    "assess_source_credibility",
    "health_check",
    "validate_critique_result",
    "format_critique_output",
    "evaluate_traceability_balance",
    "get_critic_engine",
]
