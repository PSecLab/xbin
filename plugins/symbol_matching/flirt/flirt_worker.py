import os
import xbin

@xbin.plugin(
    name="flirt_matcher",
    category="symbol_matching",
    display_name="FLIRT Matcher",
    description="Matches functions against IDA FLIRT signature database."
)
class FlirtWorker:
    def __init__(self):
        self.sig_dir = os.getenv("XBIN_FLIRT_SIG_DIR", "/app/signatures")
        self.matchers = []
        self._load_signatures()

    def _load_signatures(self):
        if not os.path.exists(self.sig_dir):
            return
        import flirt
        for root, _, files in os.walk(self.sig_dir):
            for file in files:
                if file.endswith(".sig"):
                    try:
                        with open(os.path.join(root, file), "rb") as f:
                            self.matchers.append(flirt.compile(f.read()))
                    except Exception:
                        pass
        print(f"[*] Loaded {len(self.matchers)} FLIRT signature files.")

    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "symbol_matching" not in (requested_goals or []) and "function_boundary" not in (requested_goals or []):
            print(f"[*] Symbol matching not requested for {os.path.basename(binary_path)}. Skipping.")
            return

        print(f"[*] FLIRT analyzing new binary: {binary_path}")
        if not os.path.exists(binary_path):
            print(f"[-] Binary not found at {binary_path}")
            return

        with open(binary_path, "rb") as f:
            data = f.read()

        for matcher in self.matchers:
            try:
                matches = matcher.match(data)
                for match in matches:
                    xbin.post_result(item_key="0x400000", data=str(match), confidence=1.0)
                    print(f"[+] Posted FLIRT match: {match}")
            except Exception as e:
                print(f"[-] FLIRT matching error: {e}")

    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        pass

if __name__ == "__main__":
    xbin.start_worker()
