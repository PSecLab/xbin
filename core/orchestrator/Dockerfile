FROM python:3.11-slim
WORKDIR /app

# Install Docker CLI to manage plugin containers
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Install the package in editable mode or normally
RUN pip install --no-cache-dir .

CMD ["xbin-orchestrator"]
