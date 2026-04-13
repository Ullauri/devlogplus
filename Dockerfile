# ===========================================================================
# Stage 1: Build frontend
# ===========================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ===========================================================================
# Stage 2: Python development (hot-reload, no frontend build)
# ===========================================================================
FROM python:3.12-slim AS development

WORKDIR /app

RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

COPY backend/ ./backend/
COPY alembic.ini ./

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "backend"]

# ===========================================================================
# Stage 3: Production (includes built frontend)
# ===========================================================================
FROM python:3.12-slim AS production

WORKDIR /app

RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

COPY backend/ ./backend/
COPY alembic.ini ./
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
