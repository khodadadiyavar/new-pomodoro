FROM python:3.11-slim

WORKDIR /app

COPY app ./app
COPY run.py ./run.py

ENV DEEPWORK_DB_PATH=/data/deepwork.db

EXPOSE 8000

VOLUME ["/data"]

CMD ["python", "run.py"]
