"""User-Agent rotation utilities for the crawler.

The crawler historically used a single global user agent string.  This helper
provides light-weight rotation without adding a hard dependency on browser
automation frameworks.  When enabled, callers can request a contextual
user-agent string (per domain) with deterministic fallback behaviour.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class UserAgentConfig:
    """Configuration payload for :class:`UserAgentProvider`.

    Attributes:
        pool: Optional iterable of user-agent strings to sample from.
        per_domain_overrides: Optional mapping of domain -> list of user-agent
            strings.  The provider will prefer the domain-specific list when
            available and fall back to the global pool otherwise.
        default: Final fallback user-agent string when no other value is
            configured.  If ``None``, the provider raises ``RuntimeError`` when
            asked for a value and no candidates exist.
    """

    pool: Sequence[str] | None = None
    per_domain_overrides: Mapping[str, Sequence[str]] | None = None
    default: str | None = None


class UserAgentProvider:
    """Light-weight user-agent rotation helper.

    The provider keeps no global state beyond its configuration and can be
    instantiated per crawler run.  Selection is random but stable enough for
    unit testing thanks to dependency injection of the random module (optional).
    """

    def __init__(
        self,
        config: UserAgentConfig,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._rng = rng or random.Random()

    def choose(self, *, domain: str | None = None) -> str:
        """Return a user-agent string for the given domain.

        Args:
            domain: Optional domain to look up domain-specific overrides.

        Returns:
            A user-agent string.

        Raises:
            RuntimeError: If no user-agent string could be determined.
        """

        candidates: Iterable[str] | None = None
        overrides = self._config.per_domain_overrides or {}
        if domain:
            domain = domain.lower()
            if domain in overrides:
                candidates = overrides[domain]
        if not candidates:
            candidates = self._config.pool

        if candidates:
            candidates_list = list(candidates)
            if candidates_list:
                choice = self._rng.choice(candidates_list)
                logger.debug("Selected user agent %s for domain %s", choice, domain)
                return choice

        if self._config.default:
            logger.debug(
                "Falling back to default user agent %s for domain %s",
                self._config.default,
                domain,
            )
            return self._config.default

        raise RuntimeError("UserAgentProvider has no configured user agents")
