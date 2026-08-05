FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir requests redis grpcio grpcio-tools

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY boundary_ranker.py .

ENV XBIN_ORCHESTRATOR=localhost:50051
ENV PYTHONUNBUFFERED=1

CMD ["python", "boundary_ranker.py"]
