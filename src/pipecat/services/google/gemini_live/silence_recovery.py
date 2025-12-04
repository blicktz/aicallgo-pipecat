"""Silence recovery system for Gemini Live conversations.

Monitors conversation silence and sends recovery prompts when both
the model and user have been silent for a threshold period.

Uses exponential backoff for repeated attempts, but resets when
user actively engages in conversation.
"""

import time
from dataclasses import dataclass
from loguru import logger


@dataclass
class SilenceRecoveryState:
    """State tracking for silence recovery system."""

    last_user_speech_time: float = 0.0
    last_bot_response_time: float = 0.0
    last_recovery_attempt_time: float = 0.0
    recovery_attempt_count: int = 0
    user_spoke_since_last_recovery: bool = False
    monitoring_started: bool = False  # Track if monitoring has begun
    recovery_timer_active: bool = False  # Track if recovery timer is running
    recovery_timer_start_time: float = 0.0  # When the timer was started

    def reset(self):
        """Reset recovery attempts when conversation becomes active."""
        self.recovery_attempt_count = 0
        self.user_spoke_since_last_recovery = False


class SilenceRecoverySystem:
    """Manages silence detection and recovery prompts with exponential backoff.

    Recovery timer starts when bot finishes speaking and stops when bot starts speaking again.
    Recovery is triggered when user has been silent for threshold time while timer is active.
    Uses exponential backoff (10s, 20s, 40s...) but resets when user speaks.

    Timer lifecycle:
    - STARTS: When bot finishes speaking
    - STOPS: When bot starts speaking OR when user starts speaking
    - RESETS: When user speaks (count returns to 0, timer resets to 10s)

    Monitoring begins after the bot's first response to avoid false triggers
    during initial greeting generation.
    """

    def __init__(self, initial_threshold_sec: float = 10.0):
        """Initialize silence recovery system.

        Args:
            initial_threshold_sec: Base threshold in seconds before first recovery attempt
        """
        self._state = SilenceRecoveryState()
        self._initial_threshold = initial_threshold_sec
        self._logger = logger.bind(component="SilenceRecovery")

    def start_monitoring(self) -> None:
        """Start monitoring after bot's first response.

        Should be called when bot generates its first greeting/response.
        This prevents false triggers during initial conversation setup.
        """
        if not self._state.monitoring_started:
            self._state.monitoring_started = True
            self._state.last_bot_response_time = time.time()
            self._logger.info(
                "✅ Silence recovery monitoring started (after bot's first response)",
                extra_fields={"action": "monitoring_started"},
            )

    def is_monitoring_active(self) -> bool:
        """Check if monitoring has been started."""
        return self._state.monitoring_started

    def on_user_started_speaking(self) -> None:
        """Called when user starts speaking - resets entire recovery system."""
        now = time.time()
        self._state.last_user_speech_time = now
        self._state.user_spoke_since_last_recovery = True

        # Store previous count for logging
        previous_count = self._state.recovery_attempt_count

        # Stop recovery timer
        self._state.recovery_timer_active = False
        self._state.recovery_timer_start_time = 0.0

        # Full reset: conversation is active
        self._state.reset()

        if self._state.monitoring_started:
            self._logger.debug(
                "👤 User started speaking - Recovery system reset, timer stopped",
                extra_fields={
                    "action": "user_speech_reset",
                    "previous_attempt_count": previous_count,
                },
            )

    def on_bot_started_speaking(self) -> None:
        """Called when bot starts speaking - stops the recovery timer.

        The recovery timer should only run during silence periods, not while
        the bot is actively speaking.
        """
        if self._state.recovery_timer_active:
            self._state.recovery_timer_active = False
            if self._state.monitoring_started:
                self._logger.debug(
                    "🤖 Bot started speaking - Recovery timer stopped",
                    extra_fields={"action": "bot_speaking_timer_stop"},
                )

    def on_bot_response(self) -> None:
        """Called when bot finishes speaking - starts the recovery timer.

        The timer starts after bot completes its response to measure
        user silence period. Updates last response time for logging.
        """
        now = time.time()
        self._state.last_bot_response_time = now

        # Start recovery timer when bot finishes speaking
        self._state.recovery_timer_active = True
        self._state.recovery_timer_start_time = now

        if self._state.monitoring_started:
            self._logger.debug(
                "🤖 Bot finished speaking - Recovery timer started",
                extra_fields={
                    "action": "bot_finished_timer_start",
                    "current_threshold": self._get_current_threshold(),
                },
            )

        # Don't reset counter here - bot might be responding to recovery prompt
        # Counter only resets when user speaks

    def should_trigger_recovery(self) -> bool:
        """Check if recovery should be triggered.

        Returns True only when:
        1. Monitoring has been started (after first bot response)
        2. Recovery timer is active (bot has finished speaking)
        3. User has been silent for threshold time
        4. Threshold calculated with exponential backoff
        """
        # Don't trigger before monitoring starts
        if not self._state.monitoring_started:
            return False

        # Don't trigger if timer is not active (bot is speaking)
        if not self._state.recovery_timer_active:
            return False

        now = time.time()

        # Calculate user silence duration from when timer started
        # This ensures we only track silence AFTER bot stopped speaking
        user_silence_since_timer_start = now - self._state.recovery_timer_start_time

        # Get current threshold with exponential backoff
        threshold = self._get_current_threshold()

        # Trigger if user has been silent long enough
        return user_silence_since_timer_start > threshold

    def _get_current_threshold(self) -> float:
        """Calculate current threshold with exponential backoff.

        If user spoke since last recovery, reset to base threshold.
        Otherwise, exponentially increase: 10s -> 20s -> 40s -> 80s...
        """
        if self._state.user_spoke_since_last_recovery:
            # User spoke, reset backoff
            return self._initial_threshold

        # Exponential backoff: base * (2 ^ attempt_count)
        return self._initial_threshold * (2 ** self._state.recovery_attempt_count)

    def trigger_recovery(self) -> tuple[str, dict]:
        """Trigger recovery and return (prompt, log_context).

        Returns prompt to send to model and context for logging.
        Updates internal state.
        """
        now = time.time()
        threshold = self._get_current_threshold()

        # Calculate user silence since timer started (after bot finished speaking)
        user_silence_duration = int(now - self._state.recovery_timer_start_time)

        # Prepare recovery prompt
        prompt = (
            f"The caller has been silent for {user_silence_duration} seconds "
            f"after you finished speaking. You might have missed their speech. "
            f"Please politely ask: 'Sorry, I might have missed what you said. Can you say it again?'"
        )

        # Update state
        self._state.last_recovery_attempt_time = now

        # Increment counter only if user hasn't spoken since last recovery
        if not self._state.user_spoke_since_last_recovery:
            self._state.recovery_attempt_count += 1
        else:
            # User spoke, restart from attempt 1
            self._state.recovery_attempt_count = 1

        # Mark that we haven't seen user speech since this recovery
        self._state.user_spoke_since_last_recovery = False

        # Prepare logging context
        log_context = {
            "user_silence_sec": user_silence_duration,
            "threshold_sec": threshold,
            "recovery_attempt": self._state.recovery_attempt_count,
            "next_threshold_sec": self._get_current_threshold(),
            "action": "recovery_triggered",
        }

        self._logger.warning(
            f"🔴 SILENCE DETECTED (Attempt #{self._state.recovery_attempt_count}): "
            f"User silent {user_silence_duration}s after bot finished (threshold: {threshold}s)",
            extra_fields=log_context,
        )

        return prompt, log_context

    def get_state_info(self) -> dict:
        """Get current state for debugging/monitoring."""
        now = time.time()
        return {
            "monitoring_active": self._state.monitoring_started,
            "timer_active": self._state.recovery_timer_active,
            "user_silence_since_timer_start_sec": now - self._state.recovery_timer_start_time
            if self._state.recovery_timer_active and self._state.recovery_timer_start_time > 0
            else 0,
            "user_silence_since_last_speech_sec": now - self._state.last_user_speech_time
            if self._state.last_user_speech_time > 0
            else 0,
            "current_threshold_sec": self._get_current_threshold(),
            "recovery_count": self._state.recovery_attempt_count,
            "user_spoke_since_last": self._state.user_spoke_since_last_recovery,
        }
