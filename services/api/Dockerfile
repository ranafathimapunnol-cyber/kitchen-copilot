
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api:/app
WORKDIR /app

COPY services/api/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/api/app /app/services/api/app
COPY services/api/migrations /app/services/api/migrations
COPY services/api/scripts /app/services/api/scripts
COPY services/api/tests /app/services/api/tests
COPY services/api/alembic.ini /app/services/api/alembic.ini
COPY spikes /app/spikes

WORKDIR /app/services/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
