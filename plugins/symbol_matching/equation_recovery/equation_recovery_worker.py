"""xbin producer plugin: closed-form equation recovery.

Same shape as plugins/symbol_matching/flirt/flirt_worker.py -- the worker IS the
analyzer: it gets the binary path, runs Morpheus's recovery pipeline in-process,
and posts the recovered equation string to the blackboard via post_result().

Unlike FLIRT (pure-python), this worker runs Morpheus's recover_equation(), which
needs Binary Ninja -- so its image is FROM the Morpheus base (Binja + pipeline).

Inputs per binary:
  binary_path     -- given by on_new_binary().
  iopairs path    -- DERIVED from binary_path (sibling <stem>.iopairs.txt). When
                     present, the recovery is scored/verified; else unscored.
  func            -- each address posted to the function_boundary blackboard
                     (consumed reactively in on_update); recovery runs per addr.

Reply: post_result(item_key=<binary>:<func entry addr>, data=<equation string>, confidence=...).
"""
import os
import sys

import xbin


_CORE_DIR = os.environ.get("MORPHEUS_CORE_DIR", "/project/pysindy")
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

import xbin_api  

_GOAL = "symbol_matching"


def _parse_func(spec):
    if spec in (None, ""):
        return None
    s = str(spec).strip()
    try:
        return int(s, 16) if s.lower().startswith("0x") else int(s)
    except ValueError:
        return s


@xbin.plugin(name="equation_recovery", category="symbol_matching")
class EquationRecoveryWorker:
    def __init__(self):
        # on_update() only receives (category, item_key, ...) -- no binary -- so
        # cache the announced binary here and reuse it for every function address
        # the boundary stage discovers. io_pairs are collected per function.
        self._binary_path = None
        self._active = False        # symbol_matching requested for this binary?
        self._done = set()          # func addrs already recovered (dedup)

    def on_new_binary(self, binary_path, requested_goals):
        print('[eqrec] on new binary')
        """Arm for this binary; the real work happens in on_update() once the
        function_boundary stage posts addresses."""
        self._active = _GOAL in (requested_goals or [])
        if not self._active:
            print(f"[eqrec] {_GOAL} not requested for "
                  f"{os.path.basename(binary_path)}. Skipping.")
            return
        if not os.path.exists(binary_path):
            print(f"[eqrec] binary not found: {binary_path}")
            self._active = False
            return

        # Only the binary is cached: io_pairs are collected per function address,
        # inside recover_for_function(), once the boundary stage posts one.
        self._binary_path = binary_path
        self._done = set()
        print(f"[eqrec] armed for {os.path.basename(binary_path)}; "
              f"waiting for function_boundary addresses")

    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        print(f'on updated called')
        # React to function boundaries only; the item_key IS the function addr.
        if category != "function_boundary" or not self._active \
                or not self._binary_path:
            return

        addr = _parse_func(item_key)
        print('[on update in eqn recovery]: addr found')
        if not isinstance(addr, int):
            return
        # boundary updates re-fire on every vouch/rank -- recover each addr once.
        if addr in self._done:
            return
        self._done.add(addr)

        from xbin.sdk import _current_worker
        binary_path = self._binary_path
        try:
            print(f'eqn recovery is being processed')
            # Collects io_pairs for THIS function under FastDyn, then fits.
            result = xbin_api.recover_for_function(binary_path, addr)
        except Exception as e:
            print(f"[eqrec] recovery failed for {hex(addr)}: {e!r}")
            return

        if not result:
            print(f"[eqrec] no usable io_pairs for {hex(addr)}")
            return
        equation = result.get("equation")
        if not equation:
            print(f"[eqrec] no equation recovered for {hex(addr)}")
            return

        # Key per BINARY:ADDR so different binaries/functions don't collide.
        start = (hex(result["function_start"])
                 if result.get("function_start") is not None else hex(addr))
        out_key = f"{os.path.basename(binary_path)}:{start}"
        confidence = 1.0 if result.get("verified") else (
            float(result["r2"]) if isinstance(result.get("r2"), (int, float))
            and 0.0 <= result["r2"] <= 1.0 else 0.5)

        _current_worker.post_result(item_key=out_key, data=equation,
                                    confidence=confidence)
        print(f"[eqrec] posted {out_key} (conf={confidence}): {equation}")


if __name__ == "__main__":
    xbin.start_worker()
