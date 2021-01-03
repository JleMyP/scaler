FROM python:3.8-slim as exporter

RUN pip install "poetry>=1.0.1"
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --without-hashes -o requirements.txt


FROM python:3.8-alpine

WORKDIR /app
COPY --from=exporter /app/requirements.txt ./
COPY main.py ./
RUN pip install -r requirements.txt
ENV PYTHONUNBUFFERED 1

CMD ["python", "main.py"]
