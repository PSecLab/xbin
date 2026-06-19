import os
import sys
import tempfile

import xbin

_CORE_DIR = os.environ.get("MORPHEUS_CORE_DIR", "/project/pysindy/binja_scripts")
_PYSR_DIR = os.environ.get("PYSR_DIR", "/app")
for _d in (_CORE_DIR, _PYSR_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import equation_recovery as PIPE   
import run_pysr as PYSR            

def _iopairs_path(binary_path):
    """Derive the iopairs filepath from the binary path (sibling convention)."""
    cand = os.path.splitext(binary_path)[0] + ".iopairs.txt"
    return cand if os.path.exists(cand) else None


@xbin.plugin(name="morpheus", category="symbol_matching")
class MorpheusWorker:
    def on_new_binary(self, binary_path, requested_goals):
        if "symbol_matching" not in (requested_goals or []):
            print(f"[morpheus] symbol_matching not requested for "
                  f"{os.path.basename(binary_path)}. Skipping.")
            return
        if not os.path.exists(binary_path):
            print(f"[morpheus] binary not found: {binary_path}")
            return

        io_path = _iopairs_path(binary_path)
        if not io_path:
            print(f"[morpheus] no iopairs for {os.path.basename(binary_path)} ")
            return
        try:
            names, X, y = PIPE.load_iopairs(io_path)
        except Exception as e:
            print(f"[morpheus] iopairs load failed ({io_path}): {e!r}")
            return

        out_path = os.path.join(tempfile.gettempdir(), f"morpheus_{os.path.basename(binary_path)}.expr")
        try:
            equation, loss = PYSR.run_pysr(list(names), X, y, out_path)
        except Exception as e:
            print(f"[morpheus] run_pysr failed: {e!r}")
            return

        if not equation:
            print(f"[morpheus] no equation recovered for "
                  f"{os.path.basename(binary_path)}")
            return

        from xbin.sdk import _current_worker
        if loss is None:
            confidence = 0.5
        elif loss < 1e-6:
            confidence = 1.0
        else:
            confidence = max(0.0, min(1.0, 1.0 / (1.0 + loss)))
        item_key = os.path.basename(binary_path)
        _current_worker.post_result(item_key=item_key, data=equation,
                                    confidence=confidence)
        print(f"[morpheus] posted {item_key} (conf={confidence}, "
              f"loss={loss}): {equation}")

    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        pass


if __name__ == "__main__":
    xbin.start_worker()
