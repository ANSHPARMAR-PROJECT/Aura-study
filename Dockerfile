# Build the React application first.
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Runtime image: Flask + Waitress/Gunicorn-compatible WSGI app.
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    FLASK_DEBUG=false \
    COOKIE_SECURE=true \
    AUTO_CREATE_DB=false
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY alembic.ini /app/alembic.ini
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN mkdir -p /app/backend/uploads /app/backend/backups /app/backend/logs
EXPOSE 5000
CMD ["sh", "-c", "alembic upgrade head && gunicorn --chdir backend --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-2} --timeout 120 app:app"]
