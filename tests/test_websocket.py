from bitbank_bot.exchange.websocket import parse_ticker_event


def test_parse_socketio_ticker() -> None:
    raw = (
        '42["message",{"room":"ticker_btc_jpy","message":'
        '{"last":"10000000","buy":"9990000","sell":"10010000",'
        '"high":"10100000","low":"9900000","vol":"12.3","timestamp":1}}]'
    )
    ticker = parse_ticker_event(raw, "btc_jpy")
    assert ticker is not None
    assert str(ticker.last) == "10000000"
    assert str(ticker.bid) == "9990000"
    assert str(ticker.ask) == "10010000"
