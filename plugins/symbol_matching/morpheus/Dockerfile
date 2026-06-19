# morpheus — PySR equation-recovery xbin worker (equation_recovery shape).
#
# EXTENDS the pysindy base image (Binary Ninja + the pipeline + PySR already
# installed), exactly like equation_recovery. build.sh produces that base first
# (via docker/build_docker.sh) and passes its tag in as PYSINDY_BASE; this
# Dockerfile only layers the xbin SDK + worker + the black-box run_pysr on top.
#
# Unlike eqrec it does not lift the binary -- it runs PySR (run_pysr) on the
# provided iopairs -- but it reuses the base for load_iopairs + a baked PySR.

ARG PYSINDY_BASE=pysyndy:latest
FROM ${PYSINDY_BASE}

WORKDIR /app

# xbin transport deps for the SDK.
RUN python3 -m pip install --no-cache-dir grpcio redis requests

# xbin SDK source (injected as `src/`, FLIRT pattern) on PYTHONPATH.
COPY src /opt/xbin_sdk

# Worker only. The BLACK-BOX run_pysr (+ parse_collected_data) is already baked
# into the base at /project/pysindy/pysr_script -- imported via PYSR_DIR below,
# exactly like load_iopairs is imported from binja_scripts. No local copy needed.
COPY plugins/symbol_matching/morpheus/morpheus_worker.py    /app/morpheus_worker.py

# Pre-warm Julia / SymbolicRegression.jl so the first real run isn't slow
# (juliacall otherwise precompiles lazily on the first fit). Non-fatal.
RUN python3 -c "import numpy as np; from pysr import PySRRegressor; \
m=PySRRegressor(niterations=1, populations=2, population_size=5, timeout_in_seconds=30); \
m.fit(np.array([[0.],[1.],[2.],[3.]]), np.array([0.,1.,4.,9.]))" || true

# SDK + load_iopairs + run_pysr all import from the single Binja interpreter
# (bnpython3); load_iopairs lives in binja_scripts, run_pysr in pysr_script --
# both baked into the base.
ENV MORPHEUS_CORE_DIR=/project/pysindy/binja_scripts \
    PYSR_DIR=/project/pysindy/pysr_script \
    PYTHONPATH=/opt/xbin_sdk:/opt/xbin_sdk/xbin_orchestrator:/project/pysindy/binja_scripts:/project/pysindy/pysr_script \
    XBIN_ORCHESTRATOR=localhost:50051 \
    REDIS_HOST=localhost

# Run on Binary Ninja's interpreter (load_iopairs imports binaryninja).
CMD ["/project/binaryninja/bnpython3", "/app/morpheus_worker.py"]
