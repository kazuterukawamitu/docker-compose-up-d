# Mac iTerm — 貼り付け用（超短・zsh安全）

**禁止:** Python 本体や長い `<<'HEREDOC'` を zsh に直接貼る  
（`for dquote>` / `zsh: parse error` / `no matches found` の原因）

**推奨:** 下の **1行コマンドだけ** をコピーする。パスワードは対話入力。

---

## A. いまの VPS 状態（読み取り専用・1行）

```bash
ssh rocky@49.212.212.148 'echo SERVICE; systemctl show bitbank-bot.service -p MainPID -p ActiveState -p SubState; echo PROCS; pgrep -af "bitbank_bot|launch.py" || true; echo HASH; cd /home/rocky/bitbank-bot && sha256sum src/bitbank_bot/engine.py src/bitbank_bot/orders.py src/bitbank_bot/strategy.py src/bitbank_bot/config.py'
```

## B. 誤作動 dry-run の正体確認（1行）

```bash
ssh rocky@49.212.212.148 'ps -p 634891 -o pid,ppid,etime,args; readlink /proc/634891/cwd; ps -p 634873 -o pid,ppid,etime,args'
```

## C. OOS プロトコル確認（1行）

```bash
ssh rocky@49.212.212.148 'python3 -m json.tool /home/rocky/bitbank-bot/data/validation/buy3_forward_oos_protocol.json | head -80'
```

## D. 壊れたバックアップ確認（1行）

```bash
ssh rocky@49.212.212.148 'A=/home/rocky/bitbank-backups/bitbank-source-20261105_131744.tar.gz; ls -lh "$A"; gzip -t "$A"; echo GZIP_EXIT=$?'
```

## E. 小さめ・検証付きバックアップ作成（1行・数分かかることがある）

```bash
ssh rocky@49.212.212.148 'set -e; D=/home/rocky/bitbank-backups; mkdir -p "$D"; S=$(date +%Y%m%d_%H%M%S); T="$D/clean-$S.tar.gz.tmp"; F="$D/clean-$S.tar.gz"; cd /home/rocky; tar -czf "$T" --exclude=bitbank-bot/.env --exclude=bitbank-bot/.env.\* --exclude=bitbank-bot/.venv --exclude=bitbank-bot/venv --exclude=bitbank-bot/.git --exclude=bitbank-bot/__pycache__ --exclude=bitbank-bot/logs --exclude=bitbank-bot/node_modules bitbank-bot; gzip -t "$T"; tar -tzf "$T" >/dev/null; mv "$T" "$F"; ls -lh "$F"; echo BACKUP_OK=$F'
```

## F. 監査スクリプトをファイル経由で送る（推奨・貼り付け崩れなし）

Mac でリポジトリがある場合:

```bash
scp deploy/mac/vps_readonly_audit.sh rocky@49.212.212.148:/tmp/vps_readonly_audit.sh && ssh rocky@49.212.212.148 'bash /tmp/vps_readonly_audit.sh'
```

リポジトリが無い場合（curl で生ファイル取得後）:

```bash
curl -fsSL 'https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/vps-paste-safe-audit-8008/deploy/mac/vps_readonly_audit.sh' -o /tmp/vps_readonly_audit.sh && scp /tmp/vps_readonly_audit.sh rocky@49.212.212.148:/tmp/ && ssh rocky@49.212.212.148 'bash /tmp/vps_readonly_audit.sh'
```

（PR マージ前はブランチ名を実際のブランチに合わせてください）

## G. Python を Mac で動かす正しい形（参考）

```bash
python3 <<'PY'
print("Python実行成功")
PY
```

`import os` をプロンプトに単独貼りしない。必ず `python3 <<'PY'` 〜 `PY` で囲む。

---

## いま判明している事実（ユーザー実行結果より）

| 項目 | 結果 |
| --- | --- |
| systemd `bitbank-bot.service` | **inactive / dead**（本番サービス停止中） |
| 動いているプロセス | PID **634891** = `bitbank-transfer-8delgk87` の **`--dry-run`**（16日以上） |
| 親プロセス | PID **634873** = `launch.py --dry-run` |
| VPS `engine.py` SHA-256 | `b0061d46…46d101`（過去指紋一致） |
| OOS | `shadow_only=true`, `create_order_allowed=false`, `production_enabled=false` |
| 旧バックアップ tar.gz | **壊れている**（gzip unexpected EOF） |

**LIVE は起動していない。** 実注文はこの状態では出ない。dry-run の別ディレクトリが残っているだけ。
