FROM python:3.12-slim

WORKDIR /app
COPY . /app

ENV PORT=8080 \
    DASHBOARD_DB=/data/dashboard.db \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["python3", "server.py"]
