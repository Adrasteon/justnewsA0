"""Helpers for giving ``requests`` sessions more human-like fingerprints.

This module does not attempt to replicate full browser automation.  Instead it
provides a structured way to attach plausible headers to outgoing HTTP
requests, which is sufficient for a large fraction of soft anti-bot systems.
The profiles are intentionally lightweight so they can be serialised in
configuration files when required.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field

import requests

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StealthProfile:
    """Encapsulates HTTP headers and minor behavioural tweaks."""

    user_agent: str
    accept_language: str = "en-US,en;q=0.9"
    accept_encoding: str = "gzip, deflate, br"
    headers: Mapping[str, str] = field(default_factory=dict)

    def apply_to_session(self, session: requests.Session) -> None:
        """Mutate ``session.headers`` to resemble a regular browser."""
        merged: MutableMapping[str, str] = session.headers.copy()
        merged.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Language": self.accept_language,
                "Accept-Encoding": self.accept_encoding,
            }
        )
        merged.update(self.headers)
        session.headers.clear()
        session.headers.update(merged)
        logger.debug("Applied stealth headers to session: %s", list(merged.keys()))


class StealthBrowserFactory:
    """Factory responsible for creating :class:`StealthProfile` instances."""

    def __init__(
        self,
        profiles: Sequence[Mapping[str, str]] | None = None,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._rng = rng or random.Random()
        default_profiles = [
            {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    " AppleWebKit/537.36 (KHTML, like Gecko)"
                    " Chrome/121.0.0.0 Safari/537.36"
                ),
                "accept_language": "en-US,en;q=0.9",
            },
            {
                "user_agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1)"
                    " AppleWebKit/605.1.15 (KHTML, like Gecko)"
                    " Version/17.1 Safari/605.1.15"
                ),
                "accept_language": "en-GB,en;q=0.8",
            },
            {
                "user_agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                    " (KHTML, like Gecko) Chrome/120.0.6099.216 Safari/537.36"
                ),
                "accept_language": "en-US,en;q=0.7",
            },
        ]
        raw_profiles = profiles or default_profiles
        self._profiles = []
        for profile in raw_profiles:
            # Handle both dict and StealthProfileConfig objects
            if hasattr(profile, "model_dump"):
                # It's a Pydantic model, convert to dict
                profile_dict = profile.model_dump()
            else:
                # It's already a dict
                profile_dict = profile

            if profile_dict.get("user_agent"):
                self._profiles.append(
                    StealthProfile(
                        user_agent=profile_dict["user_agent"],
                        accept_language=profile_dict.get(
                            "accept_language", "en-US,en;q=0.9"
                        ),
                        accept_encoding=profile_dict.get(
                            "accept_encoding", "gzip, deflate, br"
                        ),
                        headers=profile_dict.get("headers", {}),
                    )
                )
        if not self._profiles:
            raise ValueError("StealthBrowserFactory requires at least one profile")

    def random_profile(self) -> StealthProfile:
        """Return a random stealth profile from the configured pool."""
        profile = self._rng.choice(self._profiles)
        logger.debug("Selected stealth profile with UA %s", profile.user_agent)
        return profile

    def profile_for_user_agent(self, user_agent: str) -> StealthProfile | None:
        """Return the first profile that matches ``user_agent`` if present."""
        for profile in self._profiles:
            if profile.user_agent == user_agent:
                return profile
        return None
