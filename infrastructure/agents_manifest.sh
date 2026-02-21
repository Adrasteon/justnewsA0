#!/usr/bin/env bash
# Canonical agents manifest — single source of truth for agent names, modules and ports
# Format per-entry: name|python_module_or_placeholder|port
# - name: instance name used for systemd unit and logs
# - python_module_or_placeholder: module path used by uvicorn for dev start; placeholder for systemd-only agents
# - port: TCP port the agent listens on

AGENTS_MANIFEST=(
  "mcp_bus|agents.mcp_bus.main:app|8000"
  "chief_editor|agents.chief_editor.main:app|8001"
  # Deprecated: "scout|agents.scout.main:app|8002"
  "fact_checker|agents.fact_checker.shim:app|8018"
  "analyst|agents.analyst.main:app|8004"
  "synthesizer|agents.synthesizer.main:app|8005"
  "critic|agents.critic.main:app|8006"
  "memory|agents.memory.main:app|8007"
  "reasoning|agents.reasoning.main:app|8008"
  "newsreader|agents.newsreader.main:app|8009"
  "training_system|training_system.mcp_integration:app|8011"
  "dashboard|agents.dashboard.main:app|8013"
  "analytics|agents.analytics.dashboard:analytics_app|8012"
  # balancer removed - keep this entry deleted to avoid starting the agent
  "gpu_orchestrator|agents.gpu_orchestrator.main:app|8014"
  "archive|agents.archive.main:app|8020"
  "workflow_orchestrator|agents.workflow_orchestrator.main:app|8023"
  "crawler|agents.crawler.main:app|8022"
  "crawler_control|agents.crawler_control.main:app|8016"
)

export AGENTS_MANIFEST
