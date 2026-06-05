import xbin
import flirt
import os

@xbin.plugin(name="flirt_matcher", category="symbol_matching")
class FlirtWorker:
    def __init__(self):
        self.sig_dir = "/app/signatures"
        self.matchers = []
        self._load_signatures()

    def _load_signatures(self):
        if not os.path.exists(self.sig_dir): return
        for root, _, files in os.walk(self.sig_dir):
            for file in files:
                if file.endswith(".sig"):
                    try:
                        with open(os.path.join(root, file), "rb") as f:
                            self.matchers.append(flirt.compile(f.read()))
                    except: pass
        print(f"[*] Loaded {len(self.matchers)} FLIRT signature files.")

    def on_new_binary(self, binary_path: str):
        print(f"[*] FLIRT analyzing new binary: {binary_path}")
        if not os.path.exists(binary_path): return
        with open(binary_path, "rb") as f:
            data = f.read()

        # FLIRT matching
        from xbin.sdk import _current_worker
        for matcher in self.matchers:
            matches = matcher.match(data)
            for match in matches:
                # Post the symbol name as the data
                _current_worker.post_result(item_key="0x400000", data=str(match), confidence=1.0)

    def on_update(self, category, item_key, top_hypothesis):
        # We can listen to other analyses!
        # e.g. if we get a CFG update, we might refine our search
        if category == "cfg_generation":
            print(f"[*] CFG update received for {item_key}. Flirt might use this...")

if __name__ == "__main__":
    xbin.start_worker()
