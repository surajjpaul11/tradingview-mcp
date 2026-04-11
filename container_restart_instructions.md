# Container Restart Instructions

This file contains instructions to follow BEFORE the Docker container is restarted. Follow these steps to ensure no work or context is lost.

## Before Restart Checklist

### 1. Save all code changes
- Commit and push any uncommitted changes to the remote repository
- If work is not ready to commit, stash it: `git stash`
- Run `git status` to confirm a clean working tree

### 2. Update memory and session files
- Update `memory.md` with:
  - What you were working on (1-2 lines)
  - Current branch name
  - Today's date
- Update `last-instruction-and-plan.md` with:
  - The last instruction you were given
  - Current plan and steps (completed and remaining)
  - Set status to `IN PROGRESS` if work is ongoing, `DONE` if complete

### 3. Record active loops and cron jobs
- List all active `/loop` jobs by reading `loops.md`
- If any loops are running, ensure they are recorded in `loops.md` with job ID, interval, prompt, and date
- These will need to be recreated with `/loop` after the container restarts

### 4. Ensure all installed packages are in dependency files
- Any package you install MUST be added to the project's dependency file immediately:
  - Python: `requirements.txt`, `pyproject.toml`, or `Pipfile`
  - Node: `package.json` (use `npm install --save` or `npm install --save-dev`)
- This ensures packages are restored automatically after a restart via `pip install -r requirements.txt` or `npm install`
- Do NOT rely on memory.md to track packages — the dependency file is the source of truth

### 5. Note any running processes or servers
- If any servers or background processes are running, note their details in `memory.md`:
  - What the process is
  - The command used to start it
  - The port it runs on

## After Restart

When the container comes back up:
1. Read `memory.md`, `loops.md`, and `last-instruction-and-plan.md`
2. Recreate any `/loop` jobs listed in `loops.md`
3. Reinstall project dependencies from the dependency file (`pip install -r requirements.txt`, `npm install`, etc.)
4. Resume work from where you left off based on `last-instruction-and-plan.md`
