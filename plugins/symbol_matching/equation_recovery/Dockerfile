# equation_recovery — Morpheus xbin worker (FLIRT-worker shape).
#
# EXTENDS the pysindy base image (Binary Ninja + QEMU + Ghidra + the recovery
# pipeline) built by docker/Dockerfile. build.sh produces that base first
# (via docker/build_docker.sh) and passes its tag in as PYSINDY_BASE; this
# Dockerfile only layers the xbin SDK + worker on top so the image can register
# with the orchestrator and post_result.
#
# The worker IS the analyzer: on a new binary it runs Morpheus's recover_equation()
# in-process and posts the equation string to the blackboard -- exactly like the
# FLIRT worker runs its matcher and posts a match.
#
# xbin INJECTS its SDK into the build context (copies `src/` next to this
# Dockerfile, FLIRT pattern); build.sh stages it from the xbin checkout when the
# image is built standalone.

ARG PYSINDY_BASE=pysyndy:latest
FROM ${PYSINDY_BASE}

# ============================================================================
# xbin worker layer: equation_recovery analyzer + orchestrator communication
# ============================================================================

WORKDIR /app

# xbin transport deps for the SDK.
RUN python3 -m pip install --no-cache-dir grpcio redis requests

# xbin SDK source (injected as `src/`, FLIRT pattern). We DO NOT `pip install .`
# it: the base ships Python 3.10 and the SDK's pyproject pins requires-python
# >=3.11 (a conservative pin -- the SDK itself is plain 3.10-compatible
# gRPC/redis code). Put the SDK SOURCE on PYTHONPATH instead, which sidesteps
# the pin and imports cleanly.
COPY src /opt/xbin_sdk

# The plugin worker + in-image self-test.
COPY plugins/symbol_matching/equation_recovery/equation_recovery_worker.py /app/equation_recovery_worker.py
COPY plugins/symbol_matching/equation_recovery/selftest_in_image.py        /app/selftest_in_image.py

# SDK source (/opt/xbin_sdk + its xbin_orchestrator subdir) + recovery core all
# import from the single Binja interpreter (bnpython3 = system py3.10 + Binja).
# SDK reads XBIN_ORCHESTRATOR / REDIS_HOST from environment.
ENV MORPHEUS_CORE_DIR=/project/pysindy/binja_scripts \
    PYTHONPATH=/opt/xbin_sdk:/opt/xbin_sdk/xbin_orchestrator:/project/pysindy/binja_scripts \
    EQREC_FUNC=myfunc \
    XBIN_ORCHESTRATOR=localhost:50051 \
    REDIS_HOST=localhost

# Run the worker on Binary Ninja's interpreter (API + license needed for the lift).
CMD ["/project/binaryninja/bnpython3", "/app/equation_recovery_worker.py"]
