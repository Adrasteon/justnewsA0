# JustNews Diagrams

This folder contains a set of focused C4 diagrams that represent the JustNews agent architecture. Each diagram is
intentionally scoped to reduce cross-edge clutter and make relationships easier to reason about.

Files

- `justnews_core_infra.mmd`— Core infrastructure:`mcp_bus`,`auth`,`balancer`,`gpu_orch`.

- `justnews_ingestion_pipeline.mmd`— Ingestion stage:`scout`,`c4ai`,`crawler`,`journalist`,`memory`.

- `justnews_analysis_hitl.mmd`— Analysis & HITL
  chain:`synthesizer`,`fact_checker`,`analyst`,`critic`,`hitl`,`chief_editor`.

- `justnews_storage_dashboard.mmd`— Storage & access:`memory`,`archive`,`dashboard`,`analytics`.

- `containers/crawler_container.mmd`— Container-level view for`crawler` showing internal subsystems.

- `containers/memory_container.mmd`— Container-level view for`memory` showing internal components: MariaDB, Chroma,
  embedding cache, vector engine.

Why split into multiple diagrams

- The system is heavily interconnected; a single context diagram is too dense to read. Splitting improves readability
  and helps focus discussions on specific parts of the pipeline.

Styling & Improvements

- Relations are color-coded by domain (Green = storage, Blue = ingestion/control, Purple = analysis) to make lines
  visually thicker and more color-contrasting. No direct 'weight' property is supported in the C4 mermaid syntax, so
  color and offset are used to increase visibility.

Usage

- Use a Mermaid live editor or GitHub’s Mermaid rendering (where available) to preview `*.mmd` files.

- If you’d like me to also export PNG/SVG assets or add these diagrams to repo-as-docs, I can add an `assets/` directory
  with rendered images and link them from README.

Next steps

- I can:

- Expand container-level diagrams to cover additional heavy agents (e.g., `synthesizer`,`analyst`,`fact_checker`).

- Add a single “overview” diagram that links the per-scope diagrams as a single flow with minimal connecting edges for
  context.

- Add a script to generate fallback PNGs using Mermaid CLI or GitHub Actions.
