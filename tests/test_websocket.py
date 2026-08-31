from bitbank_bot.websocket_client import BitbankWebsocket


def test_ws_caches_ticker_trades_and_depth() -> None:
    ws = BitbankWebsocket("wss://example.invalid/socket.io/", ("ticker_btc_jpy",))
    ws._handle_42('["message",{"room_name":"ticker_btc_jpy","message":{"data":{"last":"100"}}}]')
    ws._handle_42(
        '["message",{"room_name":"transactions_btc_jpy","message":{"data":{"price":"101"}}}]'
    )
    ws._handle_42(
        '["message",{"room_name":"depth_whole_btc_jpy","message":{"data":{"asks":[]}}}]'
    )
    assert ws.last_ticker is not None
    assert ws.last_ticker["last"] == "100"
    assert ws.last_trades[-1]["price"] == "101"
    assert ws.last_depth is not None
    assert not ws.is_stale()
