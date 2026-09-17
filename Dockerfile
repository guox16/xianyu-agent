FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system xianyuagent \
    && useradd --system --gid xianyuagent --home-dir /app xianyuagent

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir /app/materials && chown -R xianyuagent:xianyuagent /app

USER xianyuagent

EXPOSE 12500

CMD ["uvicorn", "app.customer.http:app", "--host", "0.0.0.0", "--port", "12500"]
