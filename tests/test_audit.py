from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from tests.helpers import cfg


def _load_audit():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bitbank_execution_audit.py"
    spec = importlib.util.spec_from_file_location("bitbank_execution_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_source_does_not_call_create_order() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "scripts" / "bitbank_execution_audit.py"
    ).read_text(encoding="utf-8")
    assert "rest.create_order(" not in text
    assert 'private_post("/user/spot/order"' not in text
    assert "must not place orders" in text


def test_audit_public_only_when_no_keys() -> None:
    module = _load_audit()
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000", "buy": "1", "sell": "1"}
    c = cfg(api_key="", api_secret="", dry_run=True, live_trading=False)
    assert module.run_audit(c, rest) == 0
    rest.get_ticker.assert_called_once()
    rest.get_assets.assert_not_called()
    rest.get_active_orders.assert_not_called()
    rest.get_trade_history.assert_not_called()


def test_audit_with_keys_reads_private_gets_only() -> None:
    module = _load_audit()
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.get_assets.return_value = {
        "assets": [
            {"asset": "jpy", "free_amount": "1000"},
            {"asset": "btc", "free_amount": "0"},
        ]
    }
    rest.get_active_orders.return_value = []
    rest.get_trade_history.return_value = []
    c = cfg(api_key="k", api_secret="s")
    assert module.run_audit(c, rest) == 0
    rest.get_assets.assert_called_once()
    rest.get_active_orders.assert_called_once()
    rest.get_trade_history.assert_called_once()
    try:
        rest.private_post("/user/spot/order", {"pair": "btc_jpy"})
        raise AssertionError("private_post should be blocked")
    except RuntimeError as exc:
        assert "must not place" in str(exc)
