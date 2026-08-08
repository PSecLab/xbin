FROM python:3.11-slim
WORKDIR /app

# `src` is not in this directory on disk: the orchestrator injects the xbin SDK
# (plus pyproject.toml and README.md) into the build context for you.
COPY src ./src
COPY hello_worker.py .

# Putting the SDK on PYTHONPATH instead of `pip install .` keeps the
# orchestrator's server dependencies out of the worker image.
RUN pip install --no-cache-dir grpcio redis protobuf
ENV PYTHONPATH=/app/src:/app/src/xbin_orchestrator

CMD ["python", "hello_worker.py"]
