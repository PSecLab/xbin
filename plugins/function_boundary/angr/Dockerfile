FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y git build-essential libffi-dev libxml2-dev libxslt1-dev python3-dev libunicorn2 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir angr requests unicorn

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY angr_boundary_worker.py .

ENV XBIN_ORCHESTRATOR=localhost:50051
ENV PYTHONUNBUFFERED=1

CMD ["python", "angr_boundary_worker.py"]
