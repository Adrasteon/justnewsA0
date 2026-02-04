"""Cookie/consent modal heuristics for the crawler."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

try:  # Optional dependency, aligns with GenericSiteCrawler behaviour
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled gracefully at runtime
    lxml_html = None

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ModalHandlingResult:
    """Outcome of running :class:`ModalHandler` on a HTML document."""

    cleaned_html: str
    modals_detected: bool
    applied_cookies: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class ModalHandler:
    """Detect and mitigate soft-consent modals with minimal dependencies."""

    CONSENT_KEYWORDS = (
        "cookie",
        "consent",
        "gdpr",
        "preferences",
        "privacy",
        "tracking",
    )

    def __init__(
        self,
        *,
        enable_cookie_injection: bool = True,
        consent_cookie_name: str = "justnews_cookie_consent",
        consent_cookie_value: str = "1",
    ) -> None:
        self.enable_cookie_injection = enable_cookie_injection
        self.consent_cookie_name = consent_cookie_name
        self.consent_cookie_value = consent_cookie_value

    def process(self, html: str) -> ModalHandlingResult:
        """Attempt to detect and remove consent overlays.

        Args:
            html: Raw HTML string returned by the upstream request.

        Returns:
            :class:`ModalHandlingResult` describing whether any remediation took
            place.  The caller can decide how to use the cleaned HTML and
            optional cookies.
        """

        notes: list[str] = []
        detected = False
        cleaned_html = html

        if self._contains_consent_keywords(html):
            detected = True
            notes.append("Consent keywords detected in HTML")

        if lxml_html is not None and detected:
            try:
                tree = lxml_html.fromstring(html)
                removed = self._remove_overlay_nodes(tree)
                if removed:
                    cleaned_html = lxml_html.tostring(tree, encoding="unicode")
                    notes.append(f"Removed {removed} overlay nodes")
            except Exception as exc:  # noqa: BLE001 - resilience first
                logger.debug("ModalHandler failed to parse HTML: %s", exc)
                notes.append("Overlay removal failed; original HTML preserved")

        cookies: dict[str, str] = {}
        if detected and self.enable_cookie_injection:
            cookies[self.consent_cookie_name] = self.consent_cookie_value
            notes.append("Generated synthetic consent cookie")

        return ModalHandlingResult(
            cleaned_html=cleaned_html,
            modals_detected=detected,
            applied_cookies=cookies,
            notes=notes,
        )

    def _contains_consent_keywords(self, html: str) -> bool:
        lowered = html.lower()
        return any(keyword in lowered for keyword in self.CONSENT_KEYWORDS)

    def _remove_overlay_nodes(self, tree) -> int:
        """Heuristically remove modal containers from an lxml tree."""

        patterns: Iterable[str] = (
            # Original patterns - divs and sections
            "//div[contains(@class, 'cookie')]",
            "//div[contains(@class, 'consent')]",
            "//div[contains(@class, 'modal')]",
            "//div[contains(@id, 'cookie')]",
            "//div[contains(@id, 'consent')]",
            "//section[contains(@class, 'cookie')]",
            "//section[contains(@id, 'cookie')]",
            # Modern cookie banner patterns
            "//div[contains(@class, 'gdpr')]",
            "//div[contains(@class, 'privacy')]",
            "//div[contains(@class, 'banner')]",
            "//div[contains(@class, 'overlay')]",
            "//div[contains(@class, 'popup')]",
            "//div[contains(@class, 'dialog')]",
            "//div[contains(@class, 'notification')]",
            "//div[contains(@id, 'gdpr')]",
            "//div[contains(@id, 'privacy')]",
            "//div[contains(@id, 'banner')]",
            "//div[contains(@id, 'overlay')]",
            "//div[contains(@id, 'popup')]",
            "//div[contains(@id, 'dialog')]",
            "//div[contains(@id, 'notification')]",
            # Data attributes
            "//div[contains(@data-testid, 'cookie')]",
            "//div[contains(@data-testid, 'gdpr')]",
            "//div[contains(@data-testid, 'consent')]",
            "//div[contains(@data-testid, 'privacy')]",
            "//div[contains(@data-testid, 'banner')]",
            # ARIA attributes
            "//div[contains(@role, 'dialog')]",
            "//div[contains(@role, 'alertdialog')]",
            "//div[contains(@aria-label, 'cookie')]",
            "//div[contains(@aria-label, 'consent')]",
            "//div[contains(@aria-label, 'privacy')]",
            "//div[contains(@aria-label, 'gdpr')]",
            # Generic overlay patterns
            "//div[contains(@class, 'fixed') and contains(@class, 'bottom')]",
            "//div[contains(@class, 'fixed') and contains(@class, 'top')]",
            "//div[contains(@style, 'position: fixed')]",
            "//div[contains(@style, 'position:fixed')]",
            # Common framework classes
            "//div[contains(@class, 'fc-consent')]",  # Foundry CMP
            "//div[contains(@class, 'onetrust')]",  # OneTrust
            "//div[contains(@class, 'cookiebot')]",  # Cookiebot
            "//div[contains(@class, 'cmp')]",  # Generic CMP
            "//div[contains(@class, 'cc-banner')]",  # Cookie Consent
            # Other element types
            "//section[contains(@class, 'cookie')]",
            "//section[contains(@class, 'consent')]",
            "//section[contains(@class, 'gdpr')]",
            "//section[contains(@class, 'privacy')]",
            "//section[contains(@class, 'banner')]",
            "//aside[contains(@class, 'cookie')]",
            "//aside[contains(@class, 'consent')]",
            "//aside[contains(@class, 'gdpr')]",
            "//aside[contains(@class, 'privacy')]",
            "//aside[contains(@class, 'banner')]",
            # Iframes that might be cookie-related
            "//iframe[contains(@src, 'cookie')]",
            "//iframe[contains(@src, 'consent')]",
            "//iframe[contains(@src, 'gdpr')]",
            "//iframe[contains(@src, 'privacy')]",
        )
        removed = 0
        for xpath in patterns:
            for node in tree.xpath(xpath):  # type: ignore[attr-defined]
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                    removed += 1
        return removed
