"""
DEPRECATED: The NewsReader agent is deprecated. 
Its visual analysis capabilities have been superseded by the `Investigator` agent using Qwen2-VL.
Traceable screenshot capabilities have been moved to `common.web_capture`.
"""
import warnings

warnings.warn(
    "The 'agents.newsreader' package is deprecated and will be removed in a future version. "
    "Use 'agents.fact_checker.investigator' with Qwen2-VL instead.",
    DeprecationWarning,
    stacklevel=2
)
