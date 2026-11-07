# --- build the web UI
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- python app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DCF_DATA_DIR=/data DCF_STATIC_DIR=/app/static
WORKDIR /app
COPY backend/pyproject.toml ./backend/
COPY backend/dcfmc ./backend/dcfmc
RUN pip install --no-cache-dir ./backend
COPY --from=web /web/dist /app/static
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "dcfmc", "serve", "--host", "0.0.0.0", "--port", "8000"]
