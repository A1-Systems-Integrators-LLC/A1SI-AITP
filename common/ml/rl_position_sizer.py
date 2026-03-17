"""RL Position Sizer
==================
PPO-based reinforcement learning agent for dynamic position sizing.
Uses stable-baselines3 and Gymnasium.

State: [composite_score, regime_ordinal, drawdown, daily_pnl,
        fear_greed, win_rate]
Action: position size multiplier [0.2, 1.5]
Reward: risk-adjusted return (Sharpe contribution per trade).

Learns over time — no-op (returns 1.0) until trained on 100+ trades.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO

    HAS_RL = True
except ImportError:  # pragma: no cover
    HAS_RL = False
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]
    PPO = None  # type: ignore[assignment]

# ── Defaults ──────────────────────────────────────────────────────────────────
MIN_TRADES_TO_LEARN = 100
DEFAULT_MODEL_PATH = Path("models/_rl/position_sizer.zip")
MIN_MULTIPLIER = 0.2
MAX_MULTIPLIER = 1.5

# State space bounds
STATE_LOW = np.array([0.0, 0.0, -1.0, -1.0, 0.0, 0.0], dtype=np.float32)
STATE_HIGH = np.array([100.0, 6.0, 0.0, 1.0, 100.0, 1.0], dtype=np.float32)


def is_available() -> bool:
    """Check if RL dependencies are installed."""
    return HAS_RL


@dataclass
class TradeExperience:
    """Single trade experience for RL training."""

    composite_score: float  # 0-100
    regime_ordinal: int  # 0-6
    drawdown: float  # -1 to 0 (negative)
    daily_pnl: float  # -1 to 1 (fraction)
    fear_greed: float  # 0-100
    win_rate: float  # 0-1
    position_multiplier: float  # action taken (0.2-1.5)
    pnl_result: float  # actual P&L of the trade (fraction)


class TradingEnv(gym.Env if HAS_RL else object):  # type: ignore[misc]
    """Gymnasium environment for position sizing.

    Steps through historical trade experiences.
    Action: continuous [0, 1] mapped to [MIN_MULTIPLIER, MAX_MULTIPLIER].
    Reward: risk-adjusted return = pnl_result * multiplier - penalty_for_extremes.
    """

    metadata = {"render_modes": []}

    def __init__(self, experiences: list[TradeExperience]):
        if not HAS_RL:
            raise ImportError("gymnasium and stable-baselines3 required")
        super().__init__()

        self.experiences = experiences
        self._idx = 0

        # State: [composite_score, regime, drawdown, daily_pnl, fear_greed, win_rate]
        self.observation_space = spaces.Box(
            low=STATE_LOW, high=STATE_HIGH, dtype=np.float32,
        )
        # Action: single float [0, 1] mapped to [MIN_MULT, MAX_MULT]
        self.action_space = spaces.Box(
            low=np.array([0.0], dtype=np.float32),
            high=np.array([1.0], dtype=np.float32),
        )

    def _get_obs(self) -> np.ndarray:
        exp = self.experiences[self._idx]
        return np.array(
            [
                exp.composite_score,
                float(exp.regime_ordinal),
                exp.drawdown,
                exp.daily_pnl,
                exp.fear_greed,
                exp.win_rate,
            ],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple:
        super().reset(seed=seed)
        self._idx = 0
        return self._get_obs(), {}

    def step(self, action: np.ndarray) -> tuple:
        # Map action [0,1] → multiplier [MIN, MAX]
        raw_action = float(np.clip(action[0], 0.0, 1.0))
        multiplier = MIN_MULTIPLIER + raw_action * (MAX_MULTIPLIER - MIN_MULTIPLIER)

        exp = self.experiences[self._idx]

        # Reward: scaled P&L with risk penalty
        base_reward = exp.pnl_result * multiplier

        # Penalize oversizing during drawdown
        drawdown_penalty = 0.0
        if exp.drawdown < -0.1 and multiplier > 1.0:
            drawdown_penalty = -0.01 * (multiplier - 1.0) * abs(exp.drawdown)

        reward = float(base_reward + drawdown_penalty)

        self._idx += 1
        terminated = self._idx >= len(self.experiences)
        truncated = False

        obs = self._get_obs() if not terminated else np.zeros(6, dtype=np.float32)
        return obs, reward, terminated, truncated, {"multiplier": multiplier}


class RLPositionSizer:
    """PPO-based position size optimizer.

    Falls back to 1.0 multiplier when not trained or RL unavailable.
    """

    def __init__(self, model_path: Path | str | None = None):
        self._model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self._model: object | None = None
        self._trained = False

    @property
    def is_trained(self) -> bool:
        return self._trained

    def get_multiplier(
        self,
        composite_score: float,
        regime_ordinal: int,
        drawdown: float,
        daily_pnl: float,
        fear_greed: float,
        win_rate: float,
    ) -> float:
        """Get position size multiplier from the RL agent.

        Returns 1.0 if agent is not trained or RL not available.
        """
        if not HAS_RL or not self._trained or self._model is None:
            return 1.0

        obs = np.array(
            [composite_score, float(regime_ordinal), drawdown,
             daily_pnl, fear_greed, win_rate],
            dtype=np.float32,
        )
        try:
            action, _ = self._model.predict(obs, deterministic=True)
            raw = float(np.clip(action[0], 0.0, 1.0))
            multiplier = MIN_MULTIPLIER + raw * (MAX_MULTIPLIER - MIN_MULTIPLIER)
            return round(multiplier, 3)
        except Exception as e:
            logger.warning("RL prediction failed: %s", e)
            return 1.0

    def train(
        self,
        experiences: list[TradeExperience],
        total_timesteps: int = 10000,
    ) -> dict:
        """Train the PPO agent on historical trade experiences.

        Args:
            experiences: List of completed trades with outcomes.
            total_timesteps: PPO training steps.

        Returns:
            Dict with training summary.
        """
        if not HAS_RL:
            raise ImportError("gymnasium and stable-baselines3 required for RL training")

        if len(experiences) < MIN_TRADES_TO_LEARN:
            return {
                "status": "insufficient_data",
                "trades": len(experiences),
                "required": MIN_TRADES_TO_LEARN,
            }

        env = TradingEnv(experiences)
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=min(len(experiences), 2048),
            batch_size=min(len(experiences), 64),
            n_epochs=10,
            verbose=0,
        )
        model.learn(total_timesteps=total_timesteps)

        self._model = model
        self._trained = True

        # Save model
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(self._model_path))
        logger.info("RL position sizer trained on %d trades, saved to %s",
                     len(experiences), self._model_path)

        return {
            "status": "trained",
            "trades": len(experiences),
            "timesteps": total_timesteps,
            "model_path": str(self._model_path),
        }

    def load(self) -> bool:
        """Load pre-trained model from disk.

        Returns:
            True if loaded successfully.
        """
        if not HAS_RL:
            return False

        if not self._model_path.exists():
            return False

        try:
            self._model = PPO.load(str(self._model_path))
            self._trained = True
            logger.info("RL position sizer loaded from %s", self._model_path)
            return True
        except Exception as e:
            logger.warning("Failed to load RL model: %s", e)
            return False
