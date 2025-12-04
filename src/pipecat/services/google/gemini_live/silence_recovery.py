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

    def reset(self):
        """Reset recovery attempts when conversation becomes active."""
        self.recovery_attempt_count = 0
        self.user_spoke_since_last_recovery = False


class SilenceRecoverySystem:
    """Manages silence detection and recovery prompts with exponential backoff.

    Recovery is triggered only when BOTH model and user are silent for threshold time.
    Uses exponential backoff (10s, 20s, 40s...) but only when user hasn't spoken since last attempt.
    If user speaks, entire system resets to initial state.

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

        # Full reset: conversation is active
        self._state.reset()

        if self._state.monitoring_started:
            self._logger.debug(
                "👤 User started speaking - Recovery system reset",
                extra_fields={
                    "action": "user_speech_reset",
                    "previous_attempt_count": previous_count,
                },
            )

    def on_bot_response(self) -> None:
        """Called when bot generates a response.

        Updates last response time but doesn't reset counter
        (bot might be responding to recovery prompt).
        """
        self._state.last_bot_response_time = time.time()

        # Don't reset counter here - bot might be responding to recovery prompt
        # Counter only resets when user speaks

    def should_trigger_recovery(self) -> bool:
        """Check if recovery should be triggered.

        Returns True only when:
        1. Monitoring has been started (after first bot response)
        2. Both bot and user have been silent for threshold time
        3. Threshold calculated with exponential backoff
        4. If user spoke since last recovery, use base threshold (reset backoff)
        """
        # Don't trigger before monitoring starts
        if not self._state.monitoring_started:
            return False

        now = time.time()

        # Calculate silence durations
        bot_silence = (
            now - self._state.last_bot_response_time
            if self._state.last_bot_response_time > 0
            else 0
        )
        user_silence = (
            now - self._state.last_user_speech_time
            if self._state.last_user_speech_time > 0
            else 999
        )

        # Get current threshold
        threshold = self._get_current_threshold()

        # If user hasn't spoken yet (beginning of call), only check bot silence
        user_silent = (
            user_silence > threshold if self._state.last_user_speech_time > 0 else True
        )

        # Check if bot exceeded threshold AND user is silent
        bot_silent = bot_silence > threshold

        return bot_silent and user_silent

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
        bot_silence = int(now - self._state.last_bot_response_time)
        user_silence = (
            int(now - self._state.last_user_speech_time)
            if self._state.last_user_speech_time > 0
            else 0
        )

        # Prepare recovery prompt
        prompt = (
            f"You've been silent for more than {bot_silence} seconds, "
            f"and you might have missed the caller's speech during this time. "
            f"So politely ask the caller: 'Sorry, I might have missed what you said. Can you say it again?'"
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
            "bot_silence_sec": bot_silence,
            "user_silence_sec": user_silence,
            "threshold_sec": threshold,
            "recovery_attempt": self._state.recovery_attempt_count,
            "next_threshold_sec": self._get_current_threshold(),
            "action": "recovery_triggered",
        }

        self._logger.warning(
            f"🔴 SILENCE DETECTED (Attempt #{self._state.recovery_attempt_count}): "
            f"Bot silent {bot_silence}s, User silent {user_silence}s (threshold: {threshold}s)",
            extra_fields=log_context,
        )

        return prompt, log_context

    def get_state_info(self) -> dict:
        """Get current state for debugging/monitoring."""
        now = time.time()
        return {
            "monitoring_active": self._state.monitoring_started,
            "bot_silence_sec": now - self._state.last_bot_response_time
            if self._state.last_bot_response_time > 0
            else 0,
            "user_silence_sec": now - self._state.last_user_speech_time
            if self._state.last_user_speech_time > 0
            else 0,
            "current_threshold_sec": self._get_current_threshold(),
            "recovery_count": self._state.recovery_attempt_count,
            "user_spoke_since_last": self._state.user_spoke_since_last_recovery,
        }
