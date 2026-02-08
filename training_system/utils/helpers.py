"""Training System Utilities
Helper functions and tools for the online training system
"""

import json
from datetime import datetime
from typing import Any

import pandas as pd

from common.observability import get_logger

logger = get_logger(__name__)


def export_training_data_to_csv(training_data: list[dict], filename: str = None) -> str:
    """
    Export training data to CSV format

    Args:
        training_data: List of training examples
        filename: Output filename (auto-generated if None)

    Returns:
        Path to exported CSV file
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"training_data_export_{timestamp}.csv"

    try:
        # Convert to DataFrame
        df = pd.DataFrame(training_data)

        # Export to CSV
        df.to_csv(filename, index=False)

        logger.info(f"📤 Training data exported to {filename}")
        return filename

    except Exception as e:
        logger.error(f"Failed to export training data: {e}")
        raise


def calculate_training_metrics(performance_history: list[dict]) -> dict[str, Any]:
    """
    Calculate comprehensive training metrics

    Args:
        performance_history: List of performance records

    Returns:
        Dictionary of calculated metrics
    """
    if not performance_history:
        return {"error": "No performance data available"}

    try:
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(performance_history)

        # Calculate metrics
        metrics = {
            "total_updates": len(df),
            "average_accuracy_improvement": df["accuracy_after"].mean()
            - df["accuracy_before"].mean(),
            "total_examples_trained": df["examples_trained"].sum(),
            "rollback_rate": (df["rollback_triggered"].sum() / len(df)) * 100,
            "agent_performance": {},
        }

        # Per-agent metrics
        for agent in df["agent_name"].unique():
            agent_data = df[df["agent_name"] == agent]

            metrics["agent_performance"][agent] = {
                "updates_count": len(agent_data),
                "avg_accuracy_before": agent_data["accuracy_before"].mean(),
                "avg_accuracy_after": agent_data["accuracy_after"].mean(),
                "improvement": agent_data["accuracy_after"].mean()
                - agent_data["accuracy_before"].mean(),
                "total_examples": agent_data["examples_trained"].sum(),
                "rollbacks": agent_data["rollback_triggered"].sum(),
            }

        return metrics

    except Exception as e:
        logger.error(f"Failed to calculate training metrics: {e}")
        return {"error": str(e)}


def validate_training_example(example: dict[str, Any]) -> bool:
    """
    Validate training example format and content

    Args:
        example: Training example dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "agent_name",
        "task_type",
        "input_text",
        "expected_output",
        "uncertainty_score",
        "importance_score",
    ]

    try:
        # Check required fields
        for field in required_fields:
            if field not in example:
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate field types and ranges
        if not isinstance(example["uncertainty_score"], (int, float)):
            logger.warning("uncertainty_score must be numeric")
            return False

        if not 0.0 <= example["uncertainty_score"] <= 1.0:
            logger.warning("uncertainty_score must be between 0.0 and 1.0")
            return False

        if not isinstance(example["importance_score"], (int, float)):
            logger.warning("importance_score must be numeric")
            return False

        if not 0.0 <= example["importance_score"] <= 1.0:
            logger.warning("importance_score must be between 0.0 and 1.0")
            return False

        # Validate agent name
        valid_agents = [
            "scout",
            "analyst",
            "critic",
            "fact_checker",
            "synthesizer",
            "chief_editor",
            "memory",
        ]
        if example["agent_name"] not in valid_agents:
            logger.warning(f"Invalid agent_name: {example['agent_name']}")
            return False

        return True

    except Exception as e:
        logger.error(f"Training example validation failed: {e}")
        return False


def format_training_status_report(status_data: dict[str, Any]) -> str:
    """
    Format training status data into a readable report

    Args:
        status_data: Training status dictionary

    Returns:
        Formatted report string
    """
    try:
        report_lines = []
        report_lines.append("🎓 ONLINE TRAINING SYSTEM STATUS REPORT")
        report_lines.append("=" * 50)
        report_lines.append("")

        # System status
        system_status = status_data.get("system_status", {})
        report_lines.append("📊 System Status:")
        report_lines.append(
            f"   Training Active: {system_status.get('online_training_active', 'Unknown')}"
        )
        report_lines.append(
            f"   Total Examples: {system_status.get('total_training_examples', 0)}"
        )
        report_lines.append(
            f"   Agents Managed: {system_status.get('agents_managed', 0)}"
        )
        report_lines.append("")

        # Agent status
        agent_status = status_data.get("agent_status", {})
        if agent_status:
            report_lines.append("🤖 Agent Status:")
            for agent_name, status in agent_status.items():
                buffer_size = status.get("buffer_size", 0)
                threshold = status.get("update_threshold", 0)
                progress = status.get("progress_percentage", 0)
                ready_status = (
                    "🚀 READY" if status.get("update_ready", False) else "⏳ Collecting"
                )

                report_lines.append(f"   {ready_status} {agent_name}:")
                report_lines.append(
                    f"      Buffer: {buffer_size}/{threshold} examples ({progress:.1f}%)"
                )
                report_lines.append(f"      Models: {status.get('models_count', 0)}")
            report_lines.append("")

        # Training configuration
        config = status_data.get("training_configuration", {})
        if config:
            report_lines.append("⚙️ Configuration:")
            report_lines.append(
                f"   Rollback Threshold: {config.get('rollback_threshold', 0.05)}"
            )
            report_lines.append(
                f"   Performance Window: {config.get('performance_window', 100)}"
            )
            report_lines.append("")

        # Performance summary
        performance = status_data.get("model_performance", [])
        if performance:
            report_lines.append(
                f"📈 Recent Performance: {len(performance)} updates recorded"
            )
            report_lines.append("")

        report_lines.append(
            f"📅 Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"Failed to format training status report: {e}")
        return f"Error generating report: {str(e)}"


def calculate_training_efficiency(
    articles_per_hour: int, examples_percentage: float = 0.1, avg_threshold: int = 35
) -> dict[str, Any]:
    """
    Calculate training system efficiency metrics

    Args:
        articles_per_hour: Rate of article processing
        examples_percentage: Percentage of articles that generate training examples
        avg_threshold: Average training threshold across agents

    Returns:
        Efficiency metrics dictionary
    """
    try:
        # Calculate training data generation
        training_examples_per_hour = int(articles_per_hour * examples_percentage)
        examples_per_minute = training_examples_per_hour / 60

        # Calculate update frequency
        minutes_to_update = (
            avg_threshold / examples_per_minute
            if examples_per_minute > 0
            else float("inf")
        )
        updates_per_hour = 60 / minutes_to_update if minutes_to_update > 0 else 0

        # Calculate daily metrics
        hours_per_day = 24
        daily_examples = training_examples_per_hour * hours_per_day
        daily_updates = updates_per_hour * hours_per_day

        return {
            "articles_per_hour": articles_per_hour,
            "training_examples_per_hour": training_examples_per_hour,
            "examples_per_minute": round(examples_per_minute, 2),
            "minutes_to_update": round(minutes_to_update, 2),
            "updates_per_hour": round(updates_per_hour, 2),
            "daily_examples": daily_examples,
            "daily_updates": round(daily_updates, 2),
            "efficiency_rating": "Excellent"
            if updates_per_hour > 10
            else "Good"
            if updates_per_hour > 1
            else "Moderate",
        }

    except Exception as e:
        logger.error(f"Failed to calculate training efficiency: {e}")
        return {"error": str(e)}


def create_training_backup(
    training_data: dict[str, Any], backup_path: str = None
) -> str:
    """
    Create backup of training system data

    Args:
        training_data: Training system data to backup
        backup_path: Path for backup file (auto-generated if None)

    Returns:
        Path to backup file
    """
    if not backup_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"training_backup_{timestamp}.json"

    try:
        # Add metadata
        backup_data = {
            "backup_timestamp": datetime.now().isoformat(),
            "backup_version": "1.0",
            "training_data": training_data,
        }

        # Write to file
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=2, default=str)

        logger.info(f"💾 Training system backup created: {backup_path}")
        return backup_path

    except Exception as e:
        logger.error(f"Failed to create training backup: {e}")
        raise


def load_training_backup(backup_path: str) -> dict[str, Any]:
    """
    Load training system backup

    Args:
        backup_path: Path to backup file

    Returns:
        Loaded training data
    """
    try:
        with open(backup_path, encoding="utf-8") as f:
            backup_data = json.load(f)

        logger.info(f"📁 Training system backup loaded: {backup_path}")
        return backup_data.get("training_data", {})

    except Exception as e:
        logger.error(f"Failed to load training backup: {e}")
        raise
