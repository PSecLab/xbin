FROM python:3.11-slim
WORKDIR /app

# Install dependencies and git to clone signatures
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir python-flirt requests

# Copy the xbin package and install it (provides the SDK)
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Clone the FLIRT database into the container
RUN git clone --depth 1 https://github.com/maktm/flirtdb.git /app/flirtdb_repo && \
    mkdir -p /app/signatures && \
    find /app/flirtdb_repo -name "*.sig" -exec cp {} /app/signatures/ \; && \
    rm -rf /app/flirtdb_repo

# Copy the plugin script
COPY plugins/flirt/flirt_worker.py .

# Default environment variables
ENV XBIN_ORCHESTRATOR=localhost:50051
ENV XBIN_FLIRT_SIG_DIR=/app/signatures

CMD ["python", "flirt_worker.py"]
