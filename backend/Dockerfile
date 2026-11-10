FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY backend ./backend
COPY alembic.ini ./alembic.ini
EXPOSE 8000
CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
