FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock.txt .
RUN python -m pip install --no-cache-dir -r requirements.lock.txt

COPY app.py .

USER 10001:10001

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]