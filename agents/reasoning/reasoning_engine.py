"""
Reasoning Engine - Nucleoid Symbolic Reasoning Engine

This module implements the core reasoning engine using the Nucleoid symbolic
reasoning system for fact validation, contradiction detection, and explainability.

Key Components:
- NucleoidEngine: Core symbolic reasoning engine
- EnhancedReasoningEngine: News domain rules and advanced validation
- ReasoningConfig: Configuration for reasoning components

The engine provides comprehensive symbolic reasoning capabilities with
robust error handling and fallbacks.
"""

import asyncio
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx

from agents.reasoning.model_adapter import ReasoningModelAdapter
from common.observability import get_logger

# Configure logging
logger = get_logger(__name__)


class ReasoningConfig:
    """Configuration for the Reasoning Engine."""

    def __init__(self):
        self.nucleoid_config = {
            "use_local_implementation": True,
            "fallback_to_github": True,
            "github_repo": "https://github.com/nucleoidai/nucleoid.git",
            "max_facts": 10000,
            "max_rules": 1000,
        }

        self.enhanced_config = {
            "load_news_domain_rules": True,
            "enable_temporal_reasoning": True,
            "enable_orchestration_rules": True,
            "max_context_facts": 100,
        }

        self.performance_config = {
            "cache_enabled": True,
            "cache_ttl": 300,  # seconds
            "parallel_processing": True,
            "max_concurrent_queries": 4,
        }

        self.training_config = {
            "feedback_collection": True,
            "online_training": True,
            "max_feedback_buffer": 1000,
        }


# Nucleoid State Management
class NucleoidState:
    """Global state management for variables and their values."""

    def __init__(self):
        self.variable_state: dict[str, Any] = {}

    def get(self, name: str, default=None):
        return self.variable_state.get(name, default)

    def set(self, name: str, value: Any):
        self.variable_state[name] = value

    def clear(self):
        self.variable_state.clear()


class NucleoidGraph:
    """Dependency graph management using NetworkX."""

    def __init__(self):
        self.maingraph = nx.MultiDiGraph()

    def add_node(self, node_name: str):
        self.maingraph.add_node(node_name)

    def add_edge(self, from_node: str, to_node: str):
        self.maingraph.add_edge(from_node, to_node)

    def clear(self):
        self.maingraph.clear()


class ExpressionHandler:
    """Handles expression evaluation with AST parsing."""

    def __init__(self, state: NucleoidState):
        self.state = state

    def evaluate(self, node):
        """Evaluates an AST node and returns its value."""
        import ast

        if isinstance(node, ast.Name):
            if node.id in self.state.variable_state:
                return self.state.variable_state[node.id]
            else:
                raise NameError(f"Variable {node.id} is not defined")
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            else:
                raise NotImplementedError(f"Operator {type(node.op)} not supported")
        elif isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            right = self.evaluate(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            elif isinstance(node.ops[0], ast.NotEq):
                return left != right
            elif isinstance(node.ops[0], ast.Lt):
                return left < right
            elif isinstance(node.ops[0], ast.LtE):
                return left <= right
            elif isinstance(node.ops[0], ast.Gt):
                return left > right
            elif isinstance(node.ops[0], ast.GtE):
                return left >= right
            else:
                raise NotImplementedError(
                    f"Comparison operator {type(node.ops[0])} not supported"
                )
        else:
            raise NotImplementedError(f"Node type {type(node)} not supported")


class AssignmentHandler:
    """Handles variable assignments."""

    def __init__(self, state: NucleoidState, graph: NucleoidGraph):
        self.state = state
        self.graph = graph


class SimpleNucleoidImplementation:
    """Simple fallback implementation of Nucleoid for basic reasoning."""

    def __init__(self):
        self.facts: dict[str, Any] = {}
        self.rules: list[str] = []
        self.state = NucleoidState()
        self.graph = NucleoidGraph()
        self.expression_handler = ExpressionHandler(self.state)
        self.assignment_handler = AssignmentHandler(self.state, self.graph)

    def execute(self, statement: str) -> dict[str, Any]:
        """Execute a Nucleoid statement."""
        statement = statement.strip()

        # Handle variable assignments (facts) - simple assignments only
        if (
            "=" in statement
            and "==" not in statement
            and not any(op in statement for op in ["+", "-", "*", "/", "if", "then"])
        ):
            parts = statement.split("=")
            if len(parts) == 2:
                var_name = parts[0].strip()
                value = parts[1].strip()

                # Try to convert to number if possible
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    # Keep as string if not a number
                    value = value.strip("\"'")

                self.facts[var_name] = value
                self.state.set(var_name, value)
                return {
                    "success": True,
                    "message": f"Variable {var_name} set to {value}",
                }

        # Handle rule definitions (y = x + 10, if-then statements)
        if "=" in statement and (
            any(op in statement for op in ["+", "-", "*", "/"])
            or "if" in statement
            or "then" in statement
        ):
            self.rules.append(statement)
            return {"success": True, "message": "Rule added"}

        # Handle queries (single variable)
        if statement.isalpha() or statement.replace("_", "").isalpha():
            # Check if it's a direct fact
            if statement in self.facts:
                return self.facts[statement]

            # Try to evaluate using rules
            for rule in self.rules:
                if "=" in rule and rule.split("=")[0].strip() == statement:
                    right_side = rule.split("=")[1].strip()
                    try:
                        # Simple expression evaluation
                        import ast

                        tree = ast.parse(right_side, mode="eval")
                        result = self.expression_handler.evaluate(tree.body)
                        if result is not None:
                            return result
                    except Exception:
                        pass

            return {"success": False, "message": f"Unknown variable: {statement}"}

        # Handle boolean queries (==, !=, etc.)
        if any(op in statement for op in ["==", "!=", ">", "<", ">=", "<="]):
            try:
                import ast

                tree = ast.parse(statement, mode="eval")
                result = self.expression_handler.evaluate(tree.body)
                return result
            except Exception:
                return {
                    "success": False,
                    "message": "Could not evaluate boolean expression",
                }

        return {"success": False, "message": "Unknown statement type"}

    def run(self, statement: str) -> dict[str, Any]:
        """Alias for execute method to match expected interface."""
        return self.execute(statement)

    def clear(self) -> dict[str, Any]:
        """Clear all facts and rules."""
        self.facts.clear()
        self.rules.clear()
        self.state.clear()
        self.graph.clear()
        return {"success": True, "message": "Knowledge base cleared"}


class ReasoningEngine:
    """
    Core reasoning engine using Nucleoid for symbolic reasoning.

    This engine provides fact management, rule processing, and query execution
    using the Nucleoid symbolic reasoning system.
    """

    def __init__(self, config: ReasoningConfig):
        self.config = config
        self.logger = logger
        # use shared ModelAdapter (Qwen backed) wrapper
        self.mistral_adapter = ReasoningModelAdapter()

        # Core components
        self.nucleoid: Any | None = None
        self.facts_store: dict[str, Any] = {}
        self.rules_store: list[str] = []

        # Performance tracking
        self.processing_stats = {
            "total_queries": 0,
            "facts_added": 0,
            "rules_added": 0,
            "contradictions_found": 0,
            "average_processing_time": 0.0,
            "error_count": 0,
        }

        # Feedback and training
        self.feedback_buffer: list[dict[str, Any]] = []

        # Cache
        self.cache: dict[str, Any] = {}
        self.cache_timestamps: dict[str, float] = {}

        # Initialize Nucleoid
        self._initialize_nucleoid()

    def _initialize_nucleoid(self):
        """Initialize the Nucleoid reasoning engine."""
        try:
            self.logger.info("🔧 Initializing Nucleoid reasoning engine...")

            # Try to use local implementation first
            if self.config.nucleoid_config["use_local_implementation"]:
                try:
                    # Import local Nucleoid implementation
                    nucleoid_path = (
                        Path(__file__).parent.parent / "nucleoid_implementation.py"
                    )
                    if nucleoid_path.exists():
                        spec = importlib.util.spec_from_file_location(
                            "nucleoid_local", str(nucleoid_path)
                        )
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            NucleoidClass = getattr(module, "Nucleoid", None)
                            if NucleoidClass:
                                self.nucleoid = NucleoidClass()
                                self.logger.info(
                                    "✅ Local Nucleoid implementation loaded successfully"
                                )
                                return
                except Exception as e:
                    self.logger.warning(f"⚠️ Local Nucleoid implementation failed: {e}")

            # Try GitHub repository fallback
            if self.config.nucleoid_config["fallback_to_github"]:
                try:
                    nucleoid_dir = Path(__file__).parent.parent / "nucleoid_repo"
                    if not nucleoid_dir.exists():
                        self.logger.info("📥 Cloning Nucleoid repository...")
                        subprocess.run(
                            [
                                "git",
                                "clone",
                                self.config.nucleoid_config["github_repo"],
                                str(nucleoid_dir),
                            ],
                            check=True,
                            capture_output=True,
                        )

                    # Add to Python path and import
                    python_path = str(nucleoid_dir / "python")
                    if python_path not in sys.path:
                        sys.path.insert(0, python_path)

                    # Try package import
                    try:
                        import nucleoid.nucleoid as nucleoid_module  # type: ignore

                        NucleoidClass = getattr(nucleoid_module, "Nucleoid", None)
                        if NucleoidClass:
                            self.nucleoid = NucleoidClass()
                            self.logger.info(
                                "✅ GitHub Nucleoid implementation loaded successfully"
                            )
                            return
                    except ImportError:
                        pass

                    # Try file-based import
                    candidate = Path(python_path) / "nucleoid" / "nucleoid.py"
                    if candidate.exists():
                        spec = importlib.util.spec_from_file_location(
                            "nucleoid_github", str(candidate)
                        )
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            NucleoidClass = getattr(module, "Nucleoid", None)
                            if NucleoidClass:
                                self.nucleoid = NucleoidClass()
                                self.logger.info(
                                    "✅ GitHub Nucleoid implementation loaded successfully (file import)"
                                )
                                return

                except Exception as e:
                    self.logger.warning(f"⚠️ GitHub Nucleoid implementation failed: {e}")

            # Final fallback
            self.nucleoid = SimpleNucleoidImplementation()
            self.logger.info("✅ Simple Nucleoid fallback implementation loaded")

        except Exception as e:
            self.logger.error(f"❌ Nucleoid initialization failed: {e}")
            self.nucleoid = SimpleNucleoidImplementation()
            self.logger.info("✅ Using simple fallback implementation")

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics."""
        return {
            **self.processing_stats,
            "cache_size": len(self.cache),
            "feedback_buffer_size": len(self.feedback_buffer),
            "facts_store_size": len(self.facts_store),
            "rules_store_size": len(self.rules_store),
        }

    async def add_fact(self, fact_data: dict[str, Any]) -> Any:
        """Add a fact to the reasoning system."""
        import time

        start_time = time.time()

        try:
            self.processing_stats["facts_added"] += 1

            # Store fact for retrieval
            fact_id = f"fact_{len(self.facts_store)}"
            self.facts_store[fact_id] = fact_data

            # Execute fact in Nucleoid
            if self.nucleoid:
                if "statement" in fact_data:
                    # Direct statement execution
                    result = self.nucleoid.run(fact_data["statement"])
                else:
                    # Convert dict to variable assignments
                    statements = []
                    for key, value in fact_data.items():
                        if isinstance(value, str):
                            statements.append(f'{key} = "{value}"')
                        else:
                            statements.append(f"{key} = {value}")

                    result = None
                    for statement in statements:
                        result = self.nucleoid.run(statement)

                processing_time = time.time() - start_time
                self.processing_stats["average_processing_time"] = (
                    (
                        self.processing_stats["average_processing_time"]
                        * (self.processing_stats["facts_added"] - 1)
                    )
                    + processing_time
                ) / self.processing_stats["facts_added"]

                return result

            return {"success": True, "message": "Fact stored (no Nucleoid engine)"}

        except Exception as e:
            self.processing_stats["error_count"] += 1
            self.logger.error(f"Error adding fact: {e}")
            raise

    async def add_rule(self, rule: str) -> Any:
        """Add a logical rule."""
        import time

        start_time = time.time()

        try:
            self.processing_stats["rules_added"] += 1

            # Store rule for retrieval
            self.rules_store.append(rule)

            # Execute rule in Nucleoid
            if self.nucleoid:
                result = self.nucleoid.run(rule)

                processing_time = time.time() - start_time
                self.processing_stats["average_processing_time"] = (
                    (
                        self.processing_stats["average_processing_time"]
                        * (self.processing_stats["rules_added"] - 1)
                    )
                    + processing_time
                ) / self.processing_stats["rules_added"]

                return result

            return {"success": True, "message": "Rule stored (no Nucleoid engine)"}

        except Exception as e:
            self.processing_stats["error_count"] += 1
            self.logger.error(f"Error adding rule: {e}")
            raise

    async def query(self, query_str: str) -> Any:
        """Execute a symbolic reasoning query."""
        import time

        start_time = time.time()

        try:
            self.processing_stats["total_queries"] += 1

            # Check cache first
            cache_key = f"query_{hash(query_str)}"
            if self._is_cache_valid(cache_key):
                return self.cache[cache_key]

            # Execute query
            llm_task = None
            if getattr(self, "mistral_adapter", None):
                llm_task = asyncio.to_thread(self._run_llm_analysis, query_str)

            if self.nucleoid:
                result = self.nucleoid.run(query_str)

                # Cache result
                self._cache_result(cache_key, result)

                processing_time = time.time() - start_time
                self.processing_stats["average_processing_time"] = (
                    (
                        self.processing_stats["average_processing_time"]
                        * (self.processing_stats["total_queries"] - 1)
                    )
                    + processing_time
                ) / self.processing_stats["total_queries"]

                if llm_task is not None:
                    try:
                        enriched = await llm_task
                    except Exception as exc:
                        self.logger.debug("LLM reasoning task failed: %s", exc)
                        enriched = None
                    if enriched:
                        if isinstance(result, dict):
                            result = {**result, "llm_analysis": enriched}
                        else:
                            result = {"result": result, "llm_analysis": enriched}

                return result

            return {"success": False, "message": "No Nucleoid engine available"}

        except Exception as e:
            self.processing_stats["error_count"] += 1
            self.logger.error(f"Error executing query: {e}")
            raise

    async def evaluate_contradiction(self, statements: list[str]) -> dict[str, Any]:
        """Check for logical contradictions between statements."""
        try:
            contradictions = []

            # Extract variable assignments and check for direct contradictions
            variable_assignments: dict[str, Any] = {}

            for stmt in statements:
                # Check for direct variable assignments (x = 5, x = 10)
                if (
                    "=" in stmt
                    and "==" not in stmt
                    and not any(
                        op in stmt
                        for op in ["+", "-", "*", "/", "if", "then", ">", "<"]
                    )
                ):
                    parts = stmt.split("=")
                    if len(parts) == 2:
                        var_name = parts[0].strip()
                        value = parts[1].strip()

                        # Try to convert to number for comparison
                        try:
                            if "." in value:
                                value = float(value)
                            else:
                                value = int(value)
                        except ValueError:
                            value = value.strip("\"'")

                        if var_name in variable_assignments:
                            if variable_assignments[var_name] != value:
                                contradictions.append(
                                    {
                                        "statement1": f"{var_name} = {variable_assignments[var_name]}",
                                        "statement2": f"{var_name} = {value}",
                                        "conflict": "variable_reassignment_contradiction",
                                    }
                                )
                        else:
                            variable_assignments[var_name] = value

            # Check for boolean contradictions (x == 5 vs x == 10)
            boolean_statements = [
                stmt
                for stmt in statements
                if any(op in stmt for op in ["==", "!=", ">", "<", ">=", "<="])
            ]

            for i, stmt1 in enumerate(boolean_statements):
                for _j, stmt2 in enumerate(boolean_statements[i + 1 :], i + 1):
                    # Extract variable and values from boolean statements
                    try:
                        if self._are_contradictory_booleans(stmt1, stmt2):
                            contradictions.append(
                                {
                                    "statement1": stmt1,
                                    "statement2": stmt2,
                                    "conflict": "boolean_contradiction",
                                }
                            )
                    except Exception:
                        pass  # Skip if can't parse

            self.processing_stats["contradictions_found"] += len(contradictions)

            return {
                "has_contradictions": len(contradictions) > 0,
                "contradictions": contradictions,
                "total_statements": len(statements),
            }

        except Exception as e:
            self.logger.error(f"Error evaluating contradictions: {e}")
            return {
                "has_contradictions": False,
                "contradictions": [],
                "total_statements": len(statements),
            }

    def _are_contradictory_booleans(self, stmt1: str, stmt2: str) -> bool:
        """Check if two boolean statements are contradictory."""
        # Simple check for directly contradictory statements
        # e.g., "temperature == 25" vs "temperature == 30"

        # Extract variable and operator for each statement
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in stmt1 and op in stmt2:
                parts1 = stmt1.split(op)
                parts2 = stmt2.split(op)

                if len(parts1) == 2 and len(parts2) == 2:
                    var1, val1 = parts1[0].strip(), parts1[1].strip()
                    var2, val2 = parts2[0].strip(), parts2[1].strip()

                    # Same variable, same operator, different values
                    if var1 == var2 and op == "==" and val1 != val2:
                        return True

        return False

    def get_facts(self) -> dict[str, Any]:
        """Retrieve all stored facts."""
        return self.facts_store.copy()

    def get_rules(self) -> list[str]:
        """Retrieve all stored rules."""
        return self.rules_store.copy()

    def clear(self) -> dict[str, Any]:
        """Clear all facts and rules."""
        self.facts_store.clear()
        self.rules_store.clear()
        if self.nucleoid and hasattr(self.nucleoid, "clear"):
            self.nucleoid.clear()
        return {"success": True, "message": "Knowledge base cleared"}

    def log_feedback(self, operation: str, feedback_data: dict[str, Any]):
        """Log feedback for model improvement."""
        try:
            if not self.config.training_config["feedback_collection"]:
                return {"status": "feedback_collection_disabled"}

            feedback_entry = {
                "operation": operation,
                "data": feedback_data,
                "timestamp": datetime.now().isoformat(),
                "session_id": "reasoning_engine",
            }

            self.feedback_buffer.append(feedback_entry)

            # Limit buffer size
            max_buffer = self.config.training_config["max_feedback_buffer"]
            if len(self.feedback_buffer) > max_buffer:
                self.feedback_buffer = self.feedback_buffer[-max_buffer:]

            return {
                "status": "feedback_logged",
                "buffer_size": len(self.feedback_buffer),
            }

        except Exception as e:
            self.logger.error(f"Feedback logging failed: {e}")
            return {"error": str(e)}

    def get_training_status(self) -> dict[str, Any]:
        """Get training status."""
        return {
            "feedback_collection_enabled": self.config.training_config[
                "feedback_collection"
            ],
            "online_training_enabled": self.config.training_config["online_training"],
            "feedback_buffer_size": len(self.feedback_buffer),
            "facts_count": len(self.facts_store),
            "rules_count": len(self.rules_store),
        }

    def _run_llm_analysis(self, query_str: str) -> dict[str, Any] | None:
        adapter = getattr(self, "mistral_adapter", None)
        if not adapter:
            return None
        try:
            context = self._recent_facts_snapshot()
            return adapter.analyze(query_str, context)
        except Exception as exc:
            self.logger.debug("Failed to run Mistral reasoning adapter: %s", exc)
            return None

    def _recent_facts_snapshot(self, limit: int = 12) -> list[str]:
        items = list(self.facts_store.items())[-limit:]
        snapshot: list[str] = []
        for _, value in items:
            if isinstance(value, dict):
                try:
                    snapshot.append(json.dumps(value))
                    continue
                except Exception:
                    pass
            snapshot.append(str(value))
        return snapshot

    async def _ingest_neural_assessment(self, assessment: dict[str, Any]) -> list[str]:
        """Convert a NeuralAssessment into a list of statements/facts for Nucleoid."""
        stmts: list[str] = []

        # Map extracted claims directly as statements
        extracted_claims = assessment.get("extracted_claims", [])
        if isinstance(extracted_claims, list):
            for claim in extracted_claims:
                if isinstance(claim, str):
                    stmts.append(claim)
                elif isinstance(claim, dict):
                    stmts.append(str(claim))

        # Map evidence matches as facts
        evidence_matches = assessment.get("evidence_matches", [])
        if isinstance(evidence_matches, list):
            for em in evidence_matches:
                if isinstance(em, dict):
                    src = em.get("source") or em.get("source_url") or "unknown_source"
                    score = em.get("score", em.get("match_score", 0.0))
                    stmts.append(f"evidence_from_{src} = {score}")

        # Add source credibility and confidence as facts
        source_credibility = assessment.get("source_credibility")
        if source_credibility is not None:
            stmts.append(f"source_credibility = {float(source_credibility)}")

        confidence = assessment.get("confidence", 0.0)
        stmts.append(f"fact_checker_confidence = {float(confidence)}")

        return stmts

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid."""
        if not self.config.performance_config["cache_enabled"]:
            return False

        if cache_key not in self.cache_timestamps:
            return False

        import time

        cache_age = time.time() - self.cache_timestamps[cache_key]
        return cache_age < self.config.performance_config["cache_ttl"]

    def _cache_result(self, cache_key: str, result: Any):
        """Cache a result with timestamp."""
        if self.config.performance_config["cache_enabled"]:
            self.cache[cache_key] = result
            import time

            self.cache_timestamps[cache_key] = time.time()

            # Limit cache size
            if len(self.cache) > 1000:  # Configurable limit
                # Remove oldest entries
                oldest_keys = sorted(
                    self.cache_timestamps.keys(), key=lambda k: self.cache_timestamps[k]
                )[:100]
                for key in oldest_keys:
                    del self.cache[key]
                    del self.cache_timestamps[key]


class EnhancedReasoningEngine:
    """
    Enhanced reasoning engine with news domain rules and advanced validation.

    This engine extends the base ReasoningEngine with specialized rules for
    news analysis, temporal reasoning, and multi-agent orchestration.
    """

    # NEWS CREDIBILITY RULES
    NEWS_DOMAIN_RULES = [
        # Source credibility based on track record
        "if (source_age_days > 365 && fact_checks_passed > 50 && error_rate < 0.1) then source_tier = 'tier1'",
        "if (source_tier == 'tier1' && claim_controversial == false) then auto_approve_threshold = 0.7",
        "if (source_tier == 'tier1' && claim_controversial == true) then auto_approve_threshold = 0.9",
        # Breaking news validation
        "if (news_type == 'breaking' && confirmation_sources < 2) then require_manual_review = true",
        "if (news_type == 'breaking' && time_since_event < 60_minutes) then confidence_penalty = 0.2",
        # Cross-reference validation
        "if (claim_in_reuters == true && claim_in_ap == true) then cross_confirmation_bonus = 0.3",
        "if (claim_only_in_single_source == true && controversy_score > 0.8) then skepticism_flag = true",
        # Temporal consistency
        "if (quoted_event_date > publication_date) then temporal_error = true",
        "if (article_age_hours > 48 && urgency_tag == 'breaking') then stale_breaking_flag = true",
        # Multi-agent consensus
        "if (scout_confidence > 0.8 && fact_checker_score > 0.75 && analyst_sentiment == 'factual') then strong_consensus = true",
        "if (agent_agreement_count >= 3 && average_confidence > 0.85) then high_confidence_consensus = true",
        # Contradiction handling
        "if (internal_contradiction_detected == true) then credibility_score -= 0.4",
        "if (contradicts_established_fact == true) then flag_for_investigation = true",
        # Evidence strength rules
        "if (primary_sources_count >= 2 && expert_quotes >= 1) then evidence_strength = 'strong'",
        "if (evidence_strength == 'strong' && source_tier == 'tier1') then verification_confidence = 0.95",
    ]

    # TEMPORAL REASONING RULES
    TEMPORAL_RULES = [
        "if (event_timestamp > current_timestamp) then future_event_flag = true",
        "if (breaking_news_age_minutes > 180) then no_longer_breaking = true",
        "if (fact_last_updated_days > 30 && fact_volatility == 'high') then revalidation_required = true",
    ]

    # AGENT ORCHESTRATION RULES
    ORCHESTRATION_RULES = [
        "if (fact_checker_confidence < 0.6) then escalate_to_reasoning_validation = true",
        "if (scout_quality_score < 0.5) then skip_detailed_analysis = true",
        "if (multiple_agents_disagree == true) then require_chief_editor_review = true",
    ]

    def __init__(self, nucleoid_engine):
        """Initialize EnhancedReasoningEngine with a base Nucleoid engine."""
        self.nucleoid = nucleoid_engine
        self.logger = logger

        # Detect engine capabilities
        self._supports_add_rule = hasattr(self.nucleoid, "add_rule")
        self._supports_query = hasattr(self.nucleoid, "query")

        if self._supports_add_rule:
            try:
                self._load_news_domain_rules()
            except Exception as e:
                self.logger.warning(f"Could not load news domain rules: {e}")

    def _load_news_domain_rules(self):
        """Load comprehensive news domain validation rules."""
        for rule in (
            self.NEWS_DOMAIN_RULES + self.TEMPORAL_RULES + self.ORCHESTRATION_RULES
        ):
            try:
                self._add_rule(rule)
            except Exception:
                # Silently continue; engine may not be ready during import-time
                pass

    async def validate_news_claim_with_context(
        self, claim: str, article_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Advanced news validation using domain-specific logic."""
        # Add article context as facts
        for key, value in article_metadata.items():
            try:
                if isinstance(value, str):
                    await self.nucleoid.add_fact({"statement": f'{key} = "{value}"'})
                else:
                    await self.nucleoid.add_fact({"statement": f"{key} = {value}"})
            except Exception:
                continue

        # Add the claim
        try:
            await self.nucleoid.add_fact({"statement": claim, "type": "claim"})
        except Exception:
            pass

        # Query derived conclusions
        results = {
            "credibility_assessment": await self._query("source_tier"),
            "requires_review": await self._query("require_manual_review"),
            "confidence_modifier": await self._query("confidence_penalty"),
            "evidence_strength": await self._query("evidence_strength"),
            "temporal_validity": not await self._query("temporal_error"),
            "reasoning_chain": None,
        }

        return results

    async def orchestrate_multi_agent_decision(
        self, agent_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Use Nucleoid to coordinate between multiple agents."""
        # Add agent outputs as facts
        for agent, output in agent_outputs.items():
            for key, value in output.items():
                try:
                    if isinstance(value, str):
                        await self.nucleoid.add_fact(
                            {"statement": f'{agent}_{key} = "{value}"'}
                        )
                    else:
                        await self.nucleoid.add_fact(
                            {"statement": f"{agent}_{key} = {value}"}
                        )
                except Exception:
                    continue

        # Query orchestration logic
        decision = {
            "consensus_reached": await self._query("strong_consensus"),
            "confidence_level": await self._query("high_confidence_consensus"),
            "requires_escalation": await self._query("require_chief_editor_review"),
            "recommended_action": None,
            "explanation": None,
        }

        return decision

    # Adapter helpers for different Nucleoid interfaces
    async def _add_rule(self, rule: str):
        if hasattr(self.nucleoid, "add_rule"):
            return await self.nucleoid.add_rule(rule)
        if hasattr(self.nucleoid, "run"):
            return self.nucleoid.run(rule)
        raise AttributeError("Underlying engine has no add_rule or run")

    async def _add_fact(self, fact: dict[str, Any]):
        # Accept either dict with 'statement' or raw statement
        if hasattr(self.nucleoid, "add_fact"):
            return await self.nucleoid.add_fact(fact)
        if hasattr(self.nucleoid, "run"):
            stmt = fact.get("statement") if isinstance(fact, dict) else str(fact)
            return self.nucleoid.run(stmt)
        raise AttributeError("Underlying engine has no add_fact or run")

    async def _query(self, query_str: str):
        # Prefer a native `query` method if available, otherwise fall back to `run`
        if hasattr(self.nucleoid, "query"):
            try:
                return await self.nucleoid.query(query_str)
            except Exception:
                return None
        if hasattr(self.nucleoid, "run"):
            try:
                return self.nucleoid.run(query_str)
            except Exception:
                return None
        raise AttributeError("Underlying engine has no query or run")
