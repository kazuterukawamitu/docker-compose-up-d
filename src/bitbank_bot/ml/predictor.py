"""Optional ML overlay. Disabled by default; never required to trade."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from bitbank_bot.models import Snapshot

log = logging.getLogger("bitbank_bot.ml")


class Predictor:
    """Loads a joblib/sklearn-style model if present. LSTM/LightGBM/XGBoost stay optional extras."""

    def __init__(self, enabled: bool, model_path: str) -> None:
        self.enabled = enabled and bool(model_path)
        self._model: Any = None
        if self.enabled:
            path = Path(model_path)
            if not path.exists():
                log.warning("ML_MODEL_PATH %s missing; predictor disabled", path)
                self.enabled = False
                return
            try:
                import joblib  # type: ignore
            except ImportError:
                try:
                    import pickle

                    self._model = pickle.loads(path.read_bytes())
                except Exception as exc:
                    log.warning("could not load ML model: %s", exc)
                    self.enabled = False
                    return
            else:
                self._model = joblib.load(path)

    def bias(self, snapshot: Snapshot) -> str | None:
        """Return 'buy', 'sell', or None. Fail-open: errors disable the overlay."""
        if not self.enabled or self._model is None:
            return None
        try:
            close = float(snapshot.candles[-1].close)
            rsi = float(snapshot.rsi[-1]) if snapshot.rsi else 50.0
            macd = float(snapshot.macd[-1]) if snapshot.macd else 0.0
            pred = self._model.predict([[close, rsi, macd]])[0]
            if pred in {"buy", "sell", 1, -1}:
                if pred in {"buy", 1}:
                    return "buy"
                return "sell"
        except Exception as exc:
            log.warning("ML predict failed: %s", exc)
        return None
