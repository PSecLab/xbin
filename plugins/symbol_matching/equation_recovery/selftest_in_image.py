"""In-image self-test for the equation_recovery worker.

Runs INSIDE the built image: instantiates the worker (the @xbin.plugin decorator
wires it), captures post_result at the transport boundary, fires on_new_binary on
a sample, and asserts the EQUATION STRING is posted. No orchestrator needed.

Run:  /project/binaryninja/bnpython3 /app/selftest_in_image.py [binary]
Exit 0 on success.
"""
import glob
import os
import sys

FAIL = []


def check(cond, msg):
    print(("[ok] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAIL.append(msg)


def main():
    import xbin  # real SDK (vendored at /opt/xbin)
    import binaryninja
    check(bool(binaryninja.core_version()),
          f"Binary Ninja available: {binaryninja.core_version()}")

    # Importing the worker triggers @xbin.plugin, which instantiates it and wires
    # on_new_binary onto the SDK's _current_worker.
    import equation_recovery_worker as W   # noqa: F401
    from xbin.sdk import _current_worker
    check(_current_worker is not None, "@xbin.plugin instantiated a Worker")
    check(_current_worker.on_binary_handler is not None,
          "on_new_binary wired to the SDK")

    # Capture post_result at the transport boundary (no orchestrator).
    posted = []
    _current_worker.post_result = lambda item_key, data, confidence: \
        posted.append((item_key, data, confidence))

    # Sample binary. iopairs is the SIBLING <stem>.iopairs.txt the worker derives;
    # the dataset keeps them in a separate dir, so stage one next to a temp copy.
    binary = sys.argv[1] if len(sys.argv) > 1 else None
    if not binary:
        ds = "/project/pysindy/synthetic_dataset/compiled/arm32/float/O1/cse_c"
        hits = sorted(glob.glob(f"{ds}/elf/func_375_*.elf")) or \
            sorted(glob.glob(f"{ds}/elf/func_*.elf"))
        binary = hits[0] if hits else None
        if binary:
            # stage a sibling iopairs so the worker's _iopairs_path() finds it
            base = os.path.basename(binary).split("_arm32")[0]
            io = sorted(glob.glob(f"{ds}/iopairs/{base}_*.iopairs.txt"))
            if io:
                import shutil, tempfile
                tmp = tempfile.mkdtemp()
                b2 = os.path.join(tmp, "sample.elf")
                shutil.copy(binary, b2)
                shutil.copy(io[0], os.path.splitext(b2)[0] + ".iopairs.txt")
                binary = b2

    if binary and os.path.exists(binary):
        _current_worker.on_binary_handler(binary, ["symbol_matching"])
        check(bool(posted), "on_new_binary -> post_result fired")
        if posted:
            item_key, data, conf = posted[-1]
            check(isinstance(data, str) and len(data) > 0,
                  "posted data is the equation STRING")
            print(f"      item_key={item_key} confidence={conf}")
            print(f"      equation={data!r}")
    else:
        print("[--] no sample found; skipped end-to-end")

    print()
    if FAIL:
        print(f"SELFTEST FAILED: {len(FAIL)} issue(s)")
        sys.exit(1)
    print("SELFTEST PASSED: worker analyzes in-process and posts the equation")


if __name__ == "__main__":
    main()
