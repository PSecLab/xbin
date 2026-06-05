FROM python:3.11-slim
WORKDIR /app

# Install native dependencies for angr and unicorn
# Added a more comprehensive set of libraries that unicorn often needs
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    python3-dev \
    libunicorn2 \
    && rm -rf /var/lib/apt/lists/*

# Install latest stable angr
RUN pip install --no-cache-dir angr requests

# Copy xbin SDK
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Copy worker script
COPY plugins/cfg_generation/angr/angr_worker.py .

ENV XBIN_ORCHESTRATOR=localhost:50051
# Explicitly tell angr where to look for logs if needed
ENV ANGR_LOG_LEVEL=INFO

CMD ["python", "angr_worker.py"]
