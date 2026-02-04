"""Simple proxy rotation for the crawler.

The production crawler historically relied on outbound network rules to manage
rate limiting.  This helper provides a deterministic way to rotate through a
pool of HTTP(S) proxies on a per-request basis without introducing any new
runtime dependencies.  When the proxy pool is empty the helper is effectively
inactive.
"""

from __future__ import annotations

import itertools
import os
import random
import socket
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProxyDefinition:
    """Represents a single proxy entry.

    Attributes:
        url: The proxy URL in ``scheme://user:pass@host:port`` form.
        metadata: Optional metadata bundle stored alongside the entry.  This is
            primarily useful for logging and analytics (e.g. provider name).
    """

    url: str
    metadata: Mapping[str, str] | None = None


class ProxyManager:
    """Round-robin proxy iterator.

    Usage::

        manager = ProxyManager([ProxyDefinition(url="http://proxy1"), ...])
        proxy = manager.next_proxy()

    The manager is designed to be thread-safe enough for the crawler use-case
    by relying on ``itertools.cycle`` which does not mutate shared state beyond
    the iterator itself.  When the pool is empty ``next_proxy`` returns ``None``
    which signals the caller to operate without a proxy.
    """

    def __init__(self, proxies: Iterable[ProxyDefinition] | None = None) -> None:
        self._pool = list(proxies or [])
        self._cycle: Iterator[ProxyDefinition] | None = None
        if self._pool:
            self._cycle = itertools.cycle(self._pool)
            logger.info("ProxyManager initialised with %d proxies", len(self._pool))
        else:
            logger.debug("ProxyManager initialised with empty pool")

    def next_proxy(self) -> ProxyDefinition | None:
        """Return the next proxy in the rotation or ``None`` when disabled."""
        if not self._cycle:
            return None
        proxy = next(self._cycle)
        logger.debug("Selected proxy %s", proxy.url)
        return proxy


class PIASocks5Manager:
    """PIA SOCKS5 proxy manager for IP rotation.

    Provides access to Private Internet Access SOCKS5 proxy service with
    automatic credential management and connection handling.

    Usage::

        manager = PIASocks5Manager()
        proxy = manager.next_proxy()

    The PIA SOCKS5 service provides:
    - High-speed SOCKS5 proxy (10 Gbps servers)
    - Global server coverage (91 countries)
    - No usage logs
    - Automatic IP diversity through server selection
    """

    PIA_SOCKS5_HOST = "proxy-nl.privateinternetaccess.com"
    PIA_SOCKS5_PORT = 1080
    DEFAULT_REUSE_LIMIT = 10
    DEFAULT_BACKOFF_SECONDS = 1.0
    DEFAULT_BACKOFF_MAX_SECONDS = 10.0
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_VERIFY_TIMEOUT = 5.0
    COUNTRY_LOOKUP = {
        "au": "Australia",
        "br": "Brazil",
        "ca": "Canada",
        "de": "Germany",
        "es": "Spain",
        "fr": "France",
        "ie": "Ireland",
        "in": "India",
        "it": "Italy",
        "jp": "Japan",
        "mx": "Mexico",
        "nl": "Netherlands",
        "no": "Norway",
        "pl": "Poland",
        "se": "Sweden",
        "sg": "Singapore",
        "uk": "United Kingdom",
        "us": "United States",
    }

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        host: str | None = None,
        port: int | None = None,
        reuse_limit: int | None = None,
        backoff_seconds: float | None = None,
        max_backoff_seconds: float | None = None,
        max_retries: int | None = None,
        verify_timeout: float | None = None,
    ) -> None:
        """Initialize PIA SOCKS5 manager.

        Args:
            username: PIA SOCKS5 username (starts with 'x'). If None, reads from PIA_SOCKS5_USERNAME env var.
            password: PIA SOCKS5 password. If None, reads from PIA_SOCKS5_PASSWORD env var.
            host: PIA SOCKS5 host. Defaults to Netherlands server.
            port: PIA SOCKS5 port. Defaults to 1080.
        """
        self.username = username or os.getenv("PIA_SOCKS5_USERNAME")
        self.password = password or os.getenv("PIA_SOCKS5_PASSWORD")
        self.port = port or self.PIA_SOCKS5_PORT

        hosts_env = os.getenv("PIA_SOCKS5_HOSTS")
        if hosts_env:
            parsed_hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]
        else:
            parsed_hosts = []

        explicit_host = host or self.PIA_SOCKS5_HOST
        if explicit_host:
            parsed_hosts.insert(0, explicit_host)

        # Deduplicate while preserving order
        seen_hosts: set[str] = set()
        self._hosts: list[str] = []
        for value in parsed_hosts:
            if value not in seen_hosts:
                seen_hosts.add(value)
                self._hosts.append(value)

        if not self._hosts:
            self._hosts = [self.PIA_SOCKS5_HOST]

        if len(self._hosts) > 1:
            primary_host = self._hosts[0]
            alternate_hosts = self._hosts[1:]
            random.shuffle(alternate_hosts)
            self._hosts = [primary_host, *alternate_hosts]
        self._host_cycle = itertools.cycle(self._hosts)

        self.reuse_limit = reuse_limit or int(
            os.getenv("PIA_SOCKS5_REUSE_LIMIT", self.DEFAULT_REUSE_LIMIT)
        )
        self.backoff_seconds = backoff_seconds or float(
            os.getenv("PIA_SOCKS5_RELOG_BACKOFF_SECONDS", self.DEFAULT_BACKOFF_SECONDS)
        )
        self.max_backoff_seconds = max_backoff_seconds or float(
            os.getenv(
                "PIA_SOCKS5_RELOG_BACKOFF_MAX_SECONDS", self.DEFAULT_BACKOFF_MAX_SECONDS
            )
        )
        self.max_retries = max_retries or int(
            os.getenv("PIA_SOCKS5_RELOG_MAX_RETRIES", self.DEFAULT_MAX_RETRIES)
        )
        self.verify_timeout = verify_timeout or float(
            os.getenv("PIA_SOCKS5_VERIFY_TIMEOUT", self.DEFAULT_VERIFY_TIMEOUT)
        )

        self._current_host: str | None = None
        self._current_url: str | None = None
        self._base_metadata: dict[str, str] | None = None
        self._reuse_count = 0
        self._consecutive_failures = 0
        self._next_available_ts = 0.0

        if not self.username or not self.password:
            raise ValueError(
                "PIA SOCKS5 credentials not provided. Set PIA_SOCKS5_USERNAME and PIA_SOCKS5_PASSWORD environment variables."
            )

        logger.info(
            "PIA SOCKS5 manager initialized for hosts=%s:%d (reuse_limit=%d)",
            ",".join(self._hosts),
            self.port,
            self.reuse_limit,
        )

    def next_proxy(self) -> ProxyDefinition | None:
        """Get PIA SOCKS5 proxy definition (same interface as ProxyManager).

        Returns:
            ProxyDefinition with SOCKS5 URL and PIA metadata, or None if unavailable.
        """
        try:
            return self.get_proxy()
        except (ValueError, RuntimeError):
            return None

    def get_proxy(self) -> ProxyDefinition:
        """Get PIA SOCKS5 proxy definition.

        Returns:
            ProxyDefinition with SOCKS5 URL and PIA metadata.
        """
        proxy = self._ensure_active_proxy()
        metadata = dict(self._base_metadata or {})
        metadata["reuse_slot"] = f"{self._reuse_count}/{self.reuse_limit}"
        logger.debug(
            "Reusing PIA SOCKS5 proxy %s (reuse_slot=%s)",
            metadata.get("host", "unknown"),
            metadata["reuse_slot"],
        )
        return ProxyDefinition(url=proxy, metadata=metadata)

    def get_proxy_url(self) -> str:
        """Get just the SOCKS5 proxy URL string.

        Returns:
            SOCKS5 proxy URL for direct use.
        """
        return self.get_proxy().url

    @classmethod
    def is_available(cls) -> bool:
        """Check if PIA SOCKS5 credentials are available.

        Returns:
            True if credentials are configured, False otherwise.
        """
        return bool(
            os.getenv("PIA_SOCKS5_USERNAME") and os.getenv("PIA_SOCKS5_PASSWORD")
        )

    def report_failure(self, error: Exception | str | None = None) -> None:
        """Report a proxy failure to trigger reconnection and backoff."""
        reason = str(error) if error else "unknown"
        self._consecutive_failures += 1
        backoff = min(
            self.backoff_seconds * (2 ** (self._consecutive_failures - 1)),
            self.max_backoff_seconds,
        )
        jitter = random.uniform(0, min(self.backoff_seconds, backoff))
        delay = max(0.0, backoff + jitter)
        self._next_available_ts = time.monotonic() + delay
        self._current_url = None
        self._reuse_count = 0
        logger.warning(
            "PIA SOCKS5 failure detected (%s); forcing reconnect in %.1fs",
            reason,
            delay,
        )

    # Internal helpers -------------------------------------------------

    def _ensure_active_proxy(self) -> str:
        self._enforce_backoff_window()
        if self._current_url is None:
            self._refresh_connection(initial=True)
        elif self._reuse_count >= self.reuse_limit:
            self._refresh_connection(initial=False)

        # Increment reuse counter after ensuring active proxy
        self._reuse_count += 1
        return self._current_url  # type: ignore[return-value]

    def _refresh_connection(self, *, initial: bool) -> None:
        attempt = 0
        backoff = self.backoff_seconds
        max_attempts = max(1, self.max_retries)

        while attempt < max_attempts:
            host = self._select_next_host()
            if self._verify_host(host):
                self._activate_host(host)
                if attempt:
                    logger.info(
                        "PIA SOCKS5 reconnection succeeded after %d attempts",
                        attempt + 1,
                    )
                return

            attempt += 1
            if attempt >= max_attempts:
                break
            sleep_for = min(backoff, self.max_backoff_seconds)
            logger.warning(
                "PIA SOCKS5 reconnect attempt %d failed; retrying in %.1fs",
                attempt,
                sleep_for,
            )
            time.sleep(sleep_for)
            backoff = min(backoff * 2, self.max_backoff_seconds)

        raise RuntimeError("Failed to establish PIA SOCKS5 connection after retries")

    def _select_next_host(self) -> str:
        host = next(self._host_cycle)
        logger.debug("Selected PIA SOCKS5 host %s", host)
        return host

    def _verify_host(self, host: str) -> bool:
        try:
            with socket.create_connection(
                (host, self.port), timeout=self.verify_timeout
            ):
                return True
        except OSError as exc:  # pragma: no cover - network dependent
            logger.warning(
                "PIA SOCKS5 verification failed for %s:%d: %s",
                host,
                self.port,
                exc,
            )
            return False

    def _activate_host(self, host: str) -> None:
        self._current_host = host
        self._reuse_count = 0
        self._current_url = (
            f"socks5://{self.username}:{self.password}@{host}:{self.port}"
        )
        self._base_metadata = {
            "provider": "pia",
            "type": "socks5",
            "host": host,
            "port": str(self.port),
            "country": self._derive_country(host),
            "speed": "10Gbps",
        }
        self._consecutive_failures = 0
        self._next_available_ts = 0.0
        logger.info("PIA SOCKS5 connected to %s:%d", host, self.port)

    def _enforce_backoff_window(self) -> None:
        if not self._next_available_ts:
            return
        now = time.monotonic()
        if now >= self._next_available_ts:
            self._next_available_ts = 0.0
            return
        delay = self._next_available_ts - now
        logger.debug("PIA SOCKS5 backoff active; sleeping %.2fs", delay)
        time.sleep(delay)
        self._next_available_ts = 0.0

    def _derive_country(self, host: str) -> str:
        front = host.split(".")[0]
        if "-" in front:
            code = front.split("-")[-1].lower()
            return self.COUNTRY_LOOKUP.get(code, code.upper())
        return "Unknown"
