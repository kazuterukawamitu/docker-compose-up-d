from __future__ import annotations

from unittest.mock import MagicMock, patch

from bitbank_bot.websocket_client import BitbankWebsocket, recv_timed_out


def test_recv_timeout_uses_last_message_not_connect_time() -> None:
    assert not recv_timed_out(100.0, 120.0, 25.0)
    assert recv_timed_out(0.0, 101.0, 25.0)


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
