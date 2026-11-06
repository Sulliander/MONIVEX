# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt -c requirements.lock
RUN groupadd -g 10001 monivex && useradd -u 10001 -g monivex monivex && mkdir /data && chown monivex:monivex /data
COPY --chown=monivex:monivex app ./app
COPY --chown=monivex:monivex migrations ./migrations
COPY --chown=monivex:monivex --chmod=644 alembic.ini .
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
