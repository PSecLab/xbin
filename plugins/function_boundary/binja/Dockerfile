# binja — standalone Binary Ninja function_boundary xbin worker.
#
# A SELF-CONTAINED Binja image (NOT FROM the pysindy base). It mirrors only the
# Binary-Ninja portion of pysyndy/docker/Dockerfile -- Ubuntu 22.04 + py3.10 +
# the Binja install + baked license -- then layers the xbin SDK + worker. No
# Ghidra / QEMU / Morpheus pipeline.
#
# Why BN: the function START addresses this worker posts are in Binary Ninja's
# address space, the same space equation_recovery resolves against -- so
# boundaries feed straight into recover_equation(func=addr), no angr<->BN
# translation.
#
# The build context is staged by build.sh and contains: binaryninja/ (the
# install dir), license.dat, src/ (xbin SDK), and the worker.

FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /project

# Python 3.10 + pip (Binary Ninja's supported system interpreter).
RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common python3.10 python3.10-distutils curl ca-certificates \
 && curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py \
 && python3.10 /tmp/get-pip.py \
 && rm /tmp/get-pip.py \
 && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2

# Qt/X11/GL runtime libs that libbinaryninjacore / bnpython3 link against
# (same set the pysindy base installs; required even headless).
RUN apt-get install -y --no-install-recommends \
      libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-randr0 libxcb-shape0 \
      libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
      libopengl0 libegl1 libfontconfig1 libgl1 libx11-6 libxcb1 libxext6 libxrender1 \
      libfreetype6 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# xbin transport deps for the SDK (versions matched to the other worker images
# so the generated grpc/protobuf stubs import cleanly).
RUN python3 -m pip install --no-cache-dir grpcio==1.81.1 protobuf==6.33.6 redis requests

# Binary Ninja install + baked license. We use the headless API via SYSTEM
# python3 (binaryninja module on PYTHONPATH, core .so via LD_LIBRARY_PATH) --
# simpler and more robust here than bnpython3, which needs an embedded libpython.
COPY binaryninja /project/binaryninja
RUN mkdir -p /root/.binaryninja
COPY license.dat /root/.binaryninja/license.dat

# xbin SDK source (injected as `src/`, FLIRT pattern) on PYTHONPATH.
COPY src /opt/xbin_sdk
COPY binja_boundary_worker.py /app/binja_boundary_worker.py

ENV PYTHONPATH=/opt/xbin_sdk:/opt/xbin_sdk/xbin_orchestrator:/project/binaryninja/python \
    LD_LIBRARY_PATH=/project/binaryninja \
    XBIN_ORCHESTRATOR=localhost:50051 \
    REDIS_HOST=localhost

WORKDIR /app
# Headless Binary Ninja API on system python3 (license at /root/.binaryninja).
CMD ["python3", "/app/binja_boundary_worker.py"]
