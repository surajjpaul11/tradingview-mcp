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

## Git in Cowork Sessions

Cowork's shell reaches this repo through a mounted folder where files **cannot be deleted**, and it runs git 2.34. Rules:

- Work happens in the `Claude` worktree (`.claude/worktrees/Claude`, branch `claude`). Keep working on `claude` until Suraj says to merge.
- Read-only git commands always use `git --no-optional-locks ...` (plain `git status` leaves a stale `index.lock`).
- Staging and committing are allowed. Pushing is NOT possible from Cowork (remote is SSH; the Cowork shell has no SSH keys) — Suraj pushes from his Mac. Commit with per-command identity: `git -c user.name="Suraj Paul" -c user.email="suraj.j.paul@gmail.com" commit ...`.
- After any git write, move leftover `*.lock` / `tmp_obj_*` files with `mv -n` into `.git/_to_delete/`. Suraj deletes that folder periodically. Never ask for delete permission for this.
- Never run `git worktree prune` from Cowork — it cannot see Mac paths and would unlink the `Claude` worktree.
- Do not enable `worktree.useRelativePaths` (requires git ≥ 2.48; would make the repo unreadable to Cowork's git 2.34).
