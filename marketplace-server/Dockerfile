FROM python:3.12-slim
WORKDIR /app
COPY server.py .
RUN pip install --no-cache-dir fastapi uvicorn pynacl
ENV ELYSIUM_REGISTRY_ROOT=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
