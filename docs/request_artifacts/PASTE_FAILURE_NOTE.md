# Why Mac zsh exploded

Symptoms from the user paste log:

- `zsh: parse error near 'folder,'`
- `for dquote>`
- `zsh: no matches found: print(...)`
- `zsh: command not found: import`
- Incomplete SSH heredocs that re-paste over themselves mid-command

Cause: Python source and multi-hundred-line shell heredocs were pasted into **zsh**, which is not a Python interpreter. Quoting broke; `[]` and `()` triggered zsh glob/parse rules.

Fix:

1. Copy **one line** from `deploy/mac/ONE_LINERS.md` only.
2. Or `scp` `deploy/mac/vps_readonly_audit.sh` then `bash` it on the VPS.
3. For local Python: always wrap with `python3 <<'PY'` … `PY`.

Never paste `def run_step` / `for folder, dirs` into the shell prompt.
