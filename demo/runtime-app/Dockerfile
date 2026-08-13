FROM python:3.12.10-slim-bookworm

WORKDIR /app
COPY server.py /app/server.py

RUN useradd --create-home --uid 10001 runtime-demo
USER runtime-demo

EXPOSE 8000
CMD ["python", "/app/server.py"]
