# TradingView MCP — Claude Instructions

@AGENTS.md

`AGENTS.md` (imported above) holds the shared project context for all AI tools. Put tool-neutral
content there; keep only Claude-specific instructions in this file.

## On First Prompt of Session

Invoke `/session-resume` on the very first user message of this session. Do NOT invoke it again after that.

## Docker Skills

Claude skills with details for the Docker container (loaded on-demand to save tokens):
- `/docker-networking` — Server binding rules, port allocation
- `/container-restart` — Pre-restart checklist to preserve work
- `/session-resume` — Startup protocol for restoring state

## Daily Alpaca Sync (macOS)

`scripts/sync_alpaca_trades.sh` reconciles `data/trades.db` against Alpaca: corrects entry prices to
actual fills, closes rows whose position is gone at the broker, and flags open positions with no
resting stop/target (day-TIF legs expire at the close — protected orders now use GTC).

Scheduled daily at 16:00 local via launchd:

```bash
cp scripts/com.suraj.tradingview-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.suraj.tradingview-sync.plist
launchctl start com.suraj.tradingview-sync     # run once now
tail -20 data/alpaca_sync.log                  # results
```

The plist has absolute paths to this worktree — edit them if it moves. Logs: `data/alpaca_sync.log`
(script output) and `data/alpaca_sync.launchd.log` (launchd's own). Both are git-ignored.

### Auto-push (macOS)

`scripts/auto_push_claude.sh` pushes the `claude` branch when it is ahead of origin. It skips when the
working tree is dirty, a merge or rebase is in progress, the branch has diverged, or another branch is
checked out. Log: `data/auto_push.log`.

```bash
cp scripts/com.suraj.tradingview-autopush.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.suraj.tradingview-autopush.plist
launchctl start com.suraj.tradingview-autopush   # push now
tail -5 data/auto_push.log
```

## Git in Cowork Sessions

Cowork's shell reaches this repo through a mounted folder where files **cannot be deleted**, and it runs git 2.34. Rules:

- Work happens in the `Claude` worktree (`.claude/worktrees/Claude`, branch `claude`). Keep working on `claude` until Suraj says to merge.
- Read-only git commands always use `git --no-optional-locks ...` (plain `git status` leaves a stale `index.lock`).
- **Suraj's rule: every change must end up pushed.** Claude commits after each change and states plainly that the push is pending. Claude CANNOT push from Cowork (remote is SSH; the sandbox has no keys, and a credential would have to live inside the repo). Pushing happens on the Mac: `scripts/auto_push_claude.sh` runs every 15 minutes via `scripts/com.suraj.tradingview-autopush.plist` and pushes `claude` when it is ahead, clean, and not mid-merge; otherwise Suraj runs `git push origin claude`. Commit with per-command identity: `git -c user.name="Suraj Paul" -c user.email="suraj.j.paul@gmail.com" commit ...`.
- After any git write, move leftover `*.lock` / `tmp_obj_*` files with `mv -n` into `.git/_to_delete/`. Suraj deletes that folder periodically. Never ask for delete permission for this.
- Never run `git worktree prune` from Cowork — it cannot see Mac paths and would unlink the `Claude` worktree.
- Do not enable `worktree.useRelativePaths` (requires git ≥ 2.48; would make the repo unreadable to Cowork's git 2.34).
