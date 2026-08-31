from __future__ import annotations

from unittest.mock import MagicMock, patch

from bitbank_bot.websocket_client import BitbankWebsocket


def test_ws_stale_before_events() -> None:
    ws = BitbankWebsocket("wss://example/socket.io/?EIO=4&transport=websocket", ("ticker_btc_jpy",))
    assert ws.is_stale()
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
