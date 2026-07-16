"""xbin function_boundary backend: Binary Ninja.

Mirrors the angr/radare boundary workers, but uses Binary Ninja so the function
START addresses it posts are in BN's OWN address space -- the SAME space the
equation_recovery worker resolves against. That removes the angr<->BN base /
Thumb-bit mismatch entirely: a boundary posted here as hex(f.start) feeds
straight into recover_equation(func=addr) with no translation.

  e.g. this worker posts myfunc at 0x10000 (BN's address); eqrec then calls
       recover_equation(func=0x10000) and BN's get_function_at(0x10000) hits it.

Runs on Binary Ninja's interpreter (bnpython3); it needs the API + the baked
license, so its image extends the pysindy/Binja base -- exactly like the
equation_recovery worker. Same out-of-band build + .xbin-prebuilt reuse.

Reply: post_result(item_key=hex(func_start), data={end,size,name_hint}, conf=1.0)
       -- identical schema to the angr/radare boundary workers.
"""
import os

import xbin

import binaryninja as bn


# Morpheus's public seam (baked into this image). We post only the functions it
# says are recoverable -- one bb + FP in/out -- so the boundaries on the
# blackboard are the ones equation_recovery can actually consume, not every
# libm/newlib/startup routine the lift finds.
import xbin_api


def _func_size(f):
    """Byte span of a BN function (sum of its block ranges), robust to API shape."""
    try:
        tb = f.total_bytes
        if tb:
            return int(tb)
    except Exception:
        pass
    try:
        return int(sum((r.end - r.start) for r in f.address_ranges))
    except Exception:
        return 0


@xbin.plugin(name="binja", category="function_boundary")
class BinjaBoundaryWorker:
    def on_new_binary(self, binary_path, requested_goals):
        if "function_boundary" not in (requested_goals or []):
            return
        if not os.path.exists(binary_path):
            print(f"[binja-fb] binary not found: {binary_path}")
            return

        filename = os.path.basename(binary_path)
        print(f"[binja-fb] analyzing {filename} ...")
        try:
            bv = bn.load(binary_path)
            bv.update_analysis_and_wait()
        except Exception as e:
            print(f"[binja-fb] BN load failed for {filename}: {e!r}")
            return

        from xbin.sdk import _current_worker

        count = 0
        skipped = 0
        try:
            for f in bv.functions:
                if not xbin_api.is_candidate(f):
                    skipped += 1
                    continue
                size = _func_size(f)
                _current_worker.post_result(
                    item_key=hex(f.start),
                    data={
                        "end": hex(f.start + size),
                        "size": size,
                        "name_hint": f.name,
                    },
                    confidence=1.0,  # BN is authoritative for the lift eqrec uses
                )
                count += 1
            print(f"[binja-fb] posted {count} boundaries for {filename} "
                  f"(base={hex(bv.start)}; skipped {skipped} non-candidate)")
        finally:
            bv.file.close()


if __name__ == "__main__":
    xbin.start_worker()
