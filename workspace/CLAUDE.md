# Workspace — AI Coding Instructions

## Purpose
Runtime directory for generated weekly Go micro-projects.

## Structure
```
workspace/
  projects/
    .gitkeep
    2025-01-06/    ← generated project directories, named by week start date
      go.mod
      main.go
      ...
```

## Rules
- This entire directory is **git-ignored** (listed in `.gitignore`).
- The `workspace/projects/` directory is created automatically at app startup (see `main.py` lifespan).
- Each project pipeline run writes files here at `workspace/projects/<YYYY-MM-DD>/`.
- Project evaluation reads source code from these directories.
- Never store application config, secrets, or database files here.
