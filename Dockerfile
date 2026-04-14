FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py ./run.py

ENV DEEPWORK_DB_BACKEND=sqlite
ENV DEEPWORK_DB_PATH=/data/deepwork.db

EXPOSE 8000

VOLUME ["/data"]

CMD ["python", "run.py"]
