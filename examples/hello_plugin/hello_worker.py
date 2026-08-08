"""A minimal, working xbin plugin -- copy this directory to start a new tool.

Posts one hypothesis per "function" it pretends to find. Everything real a
plugin does is here in miniature: react to a new binary, post results with a
confidence, and let the orchestrator score them.

Try it against a running orchestrator without adding anything to plugins/:

    xbin-orchestrator --plugin examples/hello_plugin:symbol_matching

The plugin's declared category (below) wins over the one on the command line.
"""
import os

import xbin


@xbin.plugin(
    name="hello_matcher",
    category="symbol_matching",
    display_name="Hello Matcher",
    description="Template plugin: posts a stub symbol for a few fixed addresses.",
)
class HelloMatcher:
    def on_new_binary(self, binary_path, requested_goals):
        # `requested_goals` holds the categories the user ticked. Skip the run
        # if this plugin's category was not among them.
        if requested_goals and "symbol_matching" not in requested_goals:
            print(f"[hello] symbol_matching not requested ({requested_goals}); skipping")
            return

        size = os.path.getsize(binary_path) if os.path.exists(binary_path) else 0
        print(f"[hello] analyzing {binary_path} ({size} bytes)")

        # Item keys identify the subject of a hypothesis. Tools in one category
        # must agree on the convention so their results line up side by side --
        # here, function addresses formatted as 0x%08x.
        for offset in (0x1000, 0x2000, 0x3000):
            item_key = f"0x{offset:08x}"
            xbin.post_result(
                item_key=item_key,
                data={"known_function": f"hello_func_{offset:x}"},
                confidence=0.5,
            )
        print("[hello] posted 3 hypotheses")


if __name__ == "__main__":
    # Registers with the orchestrator, subscribes to xbin:events, and blocks.
    xbin.start_worker()
