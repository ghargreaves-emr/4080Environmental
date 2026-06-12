# Chat History (Copilot session backups)

This folder preserves the VS Code / GitHub Copilot **chat transcripts** for this
project so they are committed to Git and survive across machines and reinstalls.

## Why this exists

VS Code stores chat history **outside** the project, in your user profile:

```
%APPDATA%\Code\User\workspaceStorage\<hash>\chatSessions\*.jsonl
```

That folder is **not** part of the repo, so a normal `git push` does *not* back
up your conversations. If the profile is wiped, the history is lost even though
the code is safe on GitHub. This folder fixes that.

## Automatic snapshots (pre-commit hook)

A Git pre-commit hook in `.githooks/pre-commit` runs the export automatically on
every commit and stages the result, so chat history is captured without thinking
about it. The hook path is committed, but each clone must enable it once:

```powershell
git config core.hooksPath .githooks
```

To skip the export for a single commit, use `git commit --no-verify`.

## Manual snapshots

You can also run the export script directly whenever you want a snapshot:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\chat-history\export-chat-history.ps1
git add chat-history
git commit -m "Snapshot chat history"
git push
```

The script auto-detects the correct `workspaceStorage` folder by matching this
repo's path (the `<hash>` differs per machine, so it is not hardcoded). It copies:

| Category              | What it is                                  |
|-----------------------|---------------------------------------------|
| `chatSessions`        | Full chat transcripts (`*.jsonl`)           |
| `chatEditingSessions` | Edit / checkpoint state                     |
| `debug-logs`          | Chronicle session logs                      |

Each machine's data is stored under its own `<hash>/` subfolder, and
`last-export.json` records the most recent export.

## Restoring on a new machine

These files are a **backup/record**. To view a transcript, open the `.jsonl`
under `<hash>/chatSessions/`. To make VS Code itself show them in the Chat
history list, copy the contents of `<hash>/chatSessions/` back into that
machine's `%APPDATA%\Code\User\workspaceStorage\<new-hash>\chatSessions\`
(find `<new-hash>` via the `workspace.json` whose `folder` points at this repo).
