FROM python:3.13-slim
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server server
COPY simulation simulation
COPY database database
# Bring the database up to date, then start the server.
CMD ["sh", "-c", "python -m database.migrate && uvicorn server.main:app --host 0.0.0.0 --port 8000"]
