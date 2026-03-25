JustNews Hermes Understanding Benchmark

Goal:
- Measure whether Hermes understands and can retrieve correct justnews architecture and operations context.

Instructions:
- Answer each question with:
  - Direct answer (2-6 lines)
  - Evidence paths (at least 2 workspace file paths)
  - Confidence: high, medium, or low
- If uncertain, say what file should be checked next.

Questions:
1. Which files define local code indexing bootstrap and chat-session initialization behavior?
2. What is the fallback behavior when systemd user services are unavailable for index autoupdate?
3. Where is runtime config persisted and what API endpoint behavior is important for rollback?
4. Which files define crawler lane behavior and Crawl4AI triage related logic?
5. What is the recommended workflow for new-session context hydration?
6. Which docs are canonical entry points for project-wide documentation navigation?
7. What are the known test-scope constraints that make full-suite pytest unreliable in this workspace?
8. Which files define model mapping and recommended model defaults for agents?
9. How does query_code_index resolve tokenizer model selection order?
10. Which files govern session-start hooks and what command is run there?
11. What telemetry file is used for index events and what event types are expected?
12. What is the container-specific guidance for long-running Hermes gateway process management?

Scoring rubric:
- 2 points: correct answer with valid file evidence.
- 1 point: partially correct or weak evidence.
- 0 points: incorrect or no evidence.

Interpretation:
- 20-24: strong project understanding
- 14-19: usable but needs retrieval discipline
- 0-13: refresh memory pack and re-run bootstrap/index workflow
