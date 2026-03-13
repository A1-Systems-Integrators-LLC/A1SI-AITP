"""Circuit breaker for exchange service — prevents cascading failures."""

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is attempted while the circuit breaker is open."""

    def __init__(self, exchange_id: str, retry_after: float):
        self.exchange_id = exchange_id
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker OPEN for {exchange_id} — retry after {retry_after:.0f}s",
        )


class CircuitBreaker:
    def __init__(
        self,
        exchange_id: str,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 60,
        half_open_max_calls: int = 1,
    ) -> None:
        self.exchange_id = exchange_id
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_at: float | None = None
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check whether a call is allowed. Transitions OPEN -> HALF_OPEN if timeout elapsed."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._last_failure_at and (
                    time.monotonic() - self._last_failure_at >= self.reset_timeout_seconds
                ):
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker %s: OPEN -> HALF_OPEN", self.exchange_id)
                    return True
                return False
            # HALF_OPEN — allow up to half_open_max_calls
            return self._half_open_calls < self.half_open_max_calls

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker %s: HALF_OPEN -> CLOSED", self.exchange_id)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_at = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker %s: HALF_OPEN -> OPEN (failure in half-open)",
                    self.exchange_id,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker %s: CLOSED -> OPEN (%d failures)",
                    self.exchange_id,
                    self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_at = None
            logger.info("Circuit breaker %s: manually reset to CLOSED", self.exchange_id)

    def get_state(self) -> dict:
        with self._lock:
            return {
                "exchange_id": self.exchange_id,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_at": self._last_failure_at,
                "reset_timeout_seconds": self.reset_timeout_seconds,
            }


# Module-level registry keyed by exchange_id
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_breaker(exchange_id: str) -> CircuitBreaker:
    """Get or create a circuit breaker for the given exchange."""
    if exchange_id not in _breakers:
        with _registry_lock:
            if exchange_id not in _breakers:
                _breakers[exchange_id] = CircuitBreaker(exchange_id)
    return _breakers[exchange_id]


def get_all_breakers() -> list[dict]:
    """Return state of all registered breakers."""
    return [b.get_state() for b in _breakers.values()]


def reset_breaker(exchange_id: str) -> bool:
    """Reset a specific breaker. Returns False if not found."""
    breaker = _breakers.get(exchange_id)
    if breaker is None:
        return False
    breaker.reset()
    return True
