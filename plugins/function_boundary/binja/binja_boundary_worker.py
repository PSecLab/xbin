import os
import xbin

@xbin.plugin(
    name="binja",
    category="function_boundary",
    display_name="Binary Ninja Boundaries",
    description="Uses Binary Ninja to recover function boundary start addresses and sizes."
)
class BinjaBoundaryWorker:
    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "function_boundary" not in (requested_goals or []):
            return
        if not os.path.exists(binary_path):
            print(f"[binja-fb] binary not found: {binary_path}")
            return

        import binaryninja as bn
        import xbin_api

        filename = os.path.basename(binary_path)
        print(f"[binja-fb] analyzing {filename} ...")
        try:
            bv = bn.load(binary_path)
            bv.update_analysis_and_wait()
        except Exception as e:
            print(f"[binja-fb] BN load failed for {filename}: {e!r}")
            return

        count = 0
        skipped = 0
        try:
            for f in bv.functions:
                if hasattr(xbin_api, "is_candidate") and not xbin_api.is_candidate(f):
                    skipped += 1
                    continue
                size = getattr(f, "total_bytes", sum((r.end - r.start) for r in f.address_ranges))
                xbin.post_result(
                    item_key=hex(f.start),
                    data={
                        "end": hex(f.start + size),
                        "size": size,
                        "name_hint": f.name,
                    },
                    confidence=1.0,
                )
                count += 1
            print(f"[binja-fb] posted {count} boundaries for {filename} "
                  f"(base={hex(bv.start)}; skipped {skipped} non-candidate)")
        finally:
            bv.file.close()

if __name__ == "__main__":
    xbin.start_worker()
