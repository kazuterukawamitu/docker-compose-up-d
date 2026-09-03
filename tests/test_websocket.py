from __future__ import annotations

from unittest.mock import MagicMock, patch

from bitbank_bot.websocket_client import BitbankWebsocket


def test_ws_not_stale_before_first_event() -> None:
    ws = BitbankWebsocket("wss://example/socket.io/?EIO=4&transport=websocket", ("ticker_btc_jpy",))
    assert not ws.is_stale()
    assert not ws.is_connected()
    assert ws.last_price() is None


def test_start_without_websockets_does_not_raise() -> None:
    ws = BitbankWebsocket("wss://example", ("ticker_btc_jpy",))
    with patch.dict("sys.modules", {"websockets": None}):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("websockets"):
                raise ImportError("no ws")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", fake_import):
            ws.start()
    assert ws._thread is None


def test_ws_json_decode_failure_is_logged(caplog) -> None:
    ws = BitbankWebsocket("wss://example", ("ticker_btc_jpy",))
    with caplog.at_level("INFO", logger="bitbank_bot"):
        ws._handle_42("not-json")
    assert "json decode failed" in caplog.text
    assert ws.last_ticker is None
