# Routers — AI Coding Instructions

## Purpose
FastAPI route handlers.  These are intentionally **thin** — they parse the HTTP request, call the appropriate service function, and return a Pydantic response.

## Conventions
- Each file is one `APIRouter` with a prefix and tag.
- All registered in `__init__.py` and mounted by `main.py` under `/api/v1`.
- Database sessions are injected via `Depends(get_db)`.
- Use proper HTTP status codes: 201 for creation, 404 via `HTTPException`, etc.
- Response models are declared in the decorator (`response_model=...`).
- Never put business logic here — always delegate to `services/`.


