# docker-compose-up-d — Bitcoin moving-average backtester

A small, self-contained Python project that turns the moving-average Bitcoin
trading strategy notes in this repository into a runnable backtest. It ships
with a deterministic synthetic price generator so it runs anywhere (no API keys
or network required), and it can also backtest a CSV of real prices.

## Requirements

- Python 3.10+
- Dependencies in [`requirements.txt`](requirements.txt) (`numpy`, `pandas`, `matplotlib`)

## Setup

```bash
python3 -m pip install -r requirements.txt
```

Cloud Agents pick this up automatically via [`.cursor/environment.json`](.cursor/environment.json).

## Run

```bash
# Backtest on deterministic synthetic BTC data and save a chart
python main.py --plot backtest.png

# Tune the moving-average window / starting cash
python main.py --window 50 --cash 10000 --plot backtest.png

# Backtest against a CSV that has a `close` column
python main.py --csv prices.csv
```

Example output:

```
Backtest results
================
Initial cash    : 10,000.00
Final equity    : 8,943.54
Total return    : -10.56%
Number of trades: 70
Win rate        : 21.4%
Max drawdown    : -19.78%
```

The chart shows the price with its moving average, buy/sell markers, and the
equity curve. Results are for demonstration only and are **not** trading advice.

## Tests

```bash
python -m unittest discover -s tests
```

## Project layout

| Path | Purpose |
| --- | --- |
| `main.py` | CLI entry point: loads data, runs the backtest, prints results, saves a chart |
| `mlbot/data.py` | Synthetic price generator and CSV loader |
| `mlbot/strategy.py` | Moving-average signal generation and take-profit selection |
| `mlbot/backtest.py` | Long-only backtest engine and result metrics |
| `tests/` | Deterministic unit tests |

## Strategy specification (original notes)

The rules below are the original Japanese notes this project is based on. Docker
fragments (Japanese locale / `TZ: Japan`) are kept for reference.

```dockerfile
# Japanese
RUN apt-get update \
    && apt-get install -y locales \
    && locale-gen ja_JP.UTF-8
ENV LANG ja_JP.UTF-8
ENV LANGUAGE ja_JP:ja
ENV LC_ALL=ja_JP.UTF-8
RUN localedef -f UTF-8 -i ja_JP ja_JP.utf8
```

```yaml
web:
  environment:
    TZ: Japan
```

下降トレンドだった移動平均線が横ばいor上昇となり
Btcの価格が移動平均線を上抜けた時にbtcを可能量で買い
買った価格の➕３%で売る
移動平均線が上昇トレンド中に
Btcの価格が移動平均線を下抜けた時にbtcを可能量で買い
ゴールデンクロスの場合買った価格の➕８%で売る
ゴールデンクロス以外の場合買った価格の➕５％で売る
Btc価格が移動平均線よりも大きく５％以プラスに離れた後btc価格が下降したが移動平均線まで落ちずに
再び上昇した時にbtcを可能量で買い
買った価格の➕４%で売る
下降トレンドの移動平均線よりもbtc価格が５％以上マイナスに下降したが再び上昇した時にbtcを可能量で買い
買った価格の➕５％で売る
Btc価格が移動平均線を４％以上上昇した後下降した時に
btcを全て売る
Btc価格が下降して移動平均線クロスして下降した時に
btcを全て売る
下降トレンドの移動平均線をbtc価格がクロスして上昇した時に
Btcを全て売る
Btc価格が移動平均線よりも4％以上マイナス（extend all)に下降した後再度btc価格は上昇したが移動平均線まで上昇せずに再び下落した時に
Btcを全て売る
