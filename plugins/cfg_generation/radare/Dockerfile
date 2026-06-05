FROM python:3.11-slim
WORKDIR /app

# Install radare2 and r2pipe
# Ensure we have the latest stable debian package
RUN apt-get update && apt-get install -y git build-essential wget curl && \
    wget https://github.com/radareorg/radare2/releases/download/5.9.0/radare2_5.9.0_amd64.deb && \
    dpkg -i radare2_5.9.0_amd64.deb && \
    rm radare2_5.9.0_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir r2pipe requests

# Copy xbin SDK
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Copy worker script
COPY plugins/cfg_generation/radare/radare_worker.py .

ENV XBIN_ORCHESTRATOR=localhost:50051
CMD ["python", "radare_worker.py"]
