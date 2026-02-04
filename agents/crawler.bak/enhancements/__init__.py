"""Optional crawler enhancement modules.

Each module in this package provides an opt-in helper that augments the
existing crawler without changing its default behaviour.  The crawler engine
imports these lazily so deployments can enable the enhancements
incrementally via configuration overrides.
"""

from .modal_handler import ModalHandler, ModalHandlingResult  # noqa: F401
from .paywall_detector import PaywallDetectionResult, PaywallDetector  # noqa: F401
from .proxy_manager import PIASocks5Manager, ProxyManager  # noqa: F401
from .stealth_browser import StealthBrowserFactory, StealthProfile  # noqa: F401
from .ua_rotation import UserAgentProvider  # noqa: F401
