FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /project

RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common python3.10 python3.10-distutils curl ca-certificates \
 && curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py \
 && python3.10 /tmp/get-pip.py \
 && rm /tmp/get-pip.py \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2

RUN apt-get install -y --no-install-recommends \
      libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-randr0 libxcb-shape0 \
      libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
      libopengl0 libegl1 libfontconfig1 libgl1 libx11-6 libxcb1 libxext6 libxrender1 \
      libfreetype6 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir grpcio==1.81.1 protobuf==6.33.6 redis requests

COPY binaryninja /project/binaryninja
RUN mkdir -p /root/.binaryninja
COPY license.dat /root/.binaryninja/license.dat

COPY src /opt/xbin_sdk
COPY xbin_api.py /project/pysindy/xbin_api.py
COPY binja_scripts /project/pysindy/binja_scripts
COPY binja_boundary_worker.py /app/binja_boundary_worker.py

ENV PYTHONPATH=/opt/xbin_sdk:/opt/xbin_sdk/xbin_orchestrator:/project/binaryninja/python:/project/pysindy \
    LD_LIBRARY_PATH=/project/binaryninja \
    XBIN_ORCHESTRATOR=localhost:50051 \
    REDIS_HOST=localhost

WORKDIR /app
CMD ["python3", "/app/binja_boundary_worker.py"]
