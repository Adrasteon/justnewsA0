# JustNews V2 Training System

## Overview
The JustNews V2 Training System is an "On The Fly" active learning framework that continuously improves AI agent performance by capturing live predictions, user corrections, and implicit feedback.

## Architecture
The system relies on a centralized collection mechanism (`training_system.collect_prediction`) integrated into every AI agent.

### Data Flow
1. **Agent Execution**: An agent (e.g., Journalist, Analyst) performs a task using the Qwen-14B model via `MistralAdapter` (compatibility shim for vLLM/OpenAI API).
2. **Data Collection**: The agent's tool/engine captures the `input_text`, `prediction` (output), `task_type`, and `confidence`.
3. **Storage**: Data is stored in the `training_system` database (sqlite/postgres).
4. **Active Learning**: The `TrainingCoordinator` identifies high-value examples (low confidence or corrected) for future fine-tuning.

## Implemented Agents

All core agents are fully instrumented:

| Agent | Task Types | capture Point |
|---|---|---|
| **Chief Editor** | `quality_assessment`, `categorization`, `headline_generation` | `agents/chief_editor/tools.py` |
| **Journalist** | `generate_story_brief` (Content Extraction) | `agents/journalist/journalist_engine.py` |
| **Analyst** | `entities`, `statistics`, `sentiment`, `bias` | `agents/analyst/tools.py` |
| **Critic** | `synthesis_critique`, `neutrality`, `argument`, `fallacies` | `agents/critic/tools.py` |
| **Synthesizer** | `cluster_articles`, `aggregate_cluster`, `neutralize_text`, `summarize_article` | `agents/synthesizer/tools.py` |
| **Fact Checker** | `verify_facts`, `validate_sources`, `comprehensive_fact_check` | `agents/fact_checker/tools.py` |
| **Memory** | `embedding_optimization`, `retrieval_ranking` | `agents/memory/tools.py` |

## Data Format
Collected predictions follow this schema:
```json
{
  "agent_name": "string (e.g., 'journalist')",
  "task_type": "string (e.g., 'generate_story_brief')",
  "input_text": "string (truncated to ~5000 chars)",
  "prediction": "json_object (the agent's output)",
  "confidence": "float (0.0 - 1.0)",
  "source_url": "string (optional)",
  "timestamp": "iso8601"
}
```

## Continuous Improvement
To train adapters from this data:
1. Run `python run_training_loop.py` (future implementation).
2. The system filters for `user_corrected` or `confidence < 0.8` examples.
3. LoRA adapters are updated per-agent.

## Troubleshooting
*   **Missing Data**: Check `logs/` for "Failed to collect training data" warnings.
*   **Performance**: Data collection is asynchronous/fast and handled via try/except blocks to prevent impacting production latency.
