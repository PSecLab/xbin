"""The optional per-plugin ``xbin-plugin.toml`` manifest.

The orchestrator core carries no knowledge of any specific analysis tool. A
plugin declares the things the core would otherwise have to hardcode about it --
its consensus weight, the caches it wants bind-mounted into its container, its
``/dev/shm`` needs, and which end-to-end test tiers it belongs to -- in a
manifest file sitting next to its ``Dockerfile``.

Every field is optional and a plugin with no manifest at all keeps the generic
defaults, so this is purely additive: discovery still works off the
``Dockerfile`` + ``@xbin.plugin(...)`` decorator exactly as before.

Example::

    name     = "my_matcher"
    category = "signature_matching"
    weight   = 1.0
    shm_size = "1g"
    tiers    = ["smoke", "full"]
    e2e_timeout = 1800

    [[mounts]]
    cache  = "job_outputs"
    target = "/opt/mytool/job_outputs"

``mounts[].cache`` names a subdirectory of the orchestrator's ``CACHE_DIR``
(created world-writable on demand); ``target`` is the absolute path it appears
at inside the worker container. This is how a plugin family that needs state to
survive a container restart asks for it, without the core knowing what that
state is.
"""
import os
import re

try:                                # stdlib on the supported floor (py>=3.11)
    import tomllib as _toml
except ImportError:                 # pragma: no cover - 3.10 dev boxes
    try:
        import tomli as _toml       # type: ignore[no-redef]
    except ImportError:
        _toml = None                # type: ignore[assignment]

MANIFEST_NAME = "xbin-plugin.toml"

# Consensus weight applied to a backend that declares nothing. Matches the
# long-standing fallback in the gRPC servicer.
DEFAULT_WEIGHT = 0.5

# Docker's default /dev/shm is 64m, which is too small for workers that boot an
# emulator. Kept generous by default so no plugin has to opt in to work, and
# overridable per-plugin (shm_size) or fleet-wide (XBIN_DEFAULT_SHM_SIZE).
DEFAULT_SHM_SIZE = os.getenv("XBIN_DEFAULT_SHM_SIZE", "1g")

_SAFE_CACHE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def read_manifest(plugin_dir):
    """Return the parsed manifest for ``plugin_dir``, or ``{}`` if there isn't
    a readable one. Never raises: a malformed manifest degrades to defaults
    rather than taking the orchestrator down at discovery time."""
    if not plugin_dir or not os.path.isdir(plugin_dir):
        return {}
    path = os.path.join(plugin_dir, MANIFEST_NAME)
    if not os.path.exists(path) or _toml is None:
        return {}
    try:
        with open(path, "rb") as fh:
            data = _toml.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def manifest_weight(manifest):
    """Consensus weight declared by a manifest, clamped to [0.0, 1.0]."""
    try:
        return max(0.0, min(1.0, float(manifest["weight"])))
    except (KeyError, TypeError, ValueError):
        return None


def manifest_mounts(manifest, cache_dir):
    """Yield ``(host_path, container_path)`` for each declared cache mount.

    ``cache`` is restricted to a plain directory name so a manifest can never
    point the bind-mount at an arbitrary host path, and ``target`` must be
    absolute for Docker to accept it. Anything else is skipped."""
    for entry in manifest.get("mounts", []) or []:
        if not isinstance(entry, dict):
            continue
        cache = entry.get("cache")
        target = entry.get("target")
        if not cache or not target:
            continue
        if not _SAFE_CACHE_NAME.match(str(cache)) or str(cache) in (".", ".."):
            continue
        if not str(target).startswith("/"):
            continue
        yield os.path.join(cache_dir, str(cache)), str(target)


def manifest_shm_size(manifest):
    value = manifest.get("shm_size")
    return str(value) if value else DEFAULT_SHM_SIZE


def iter_plugin_dirs(plugin_dirs, explicit_plugins=()):
    """Yield every directory the orchestrator would treat as a plugin.

    Mirrors the discovery walk in ``list_available_plugins`` -- a directory
    qualifies when it holds a file named exactly ``Dockerfile``. Shared
    base-image bundles under ``plugins/_bases/`` therefore stay invisible here
    as long as they name their build file something else."""
    seen = set()
    for pdir in plugin_dirs or ():
        if not pdir or not os.path.exists(pdir):
            continue
        for root, _dirs, files in os.walk(pdir):
            if "Dockerfile" in files and root not in seen:
                seen.add(root)
                yield root
    for path, _category in explicit_plugins or ():
        if not path or not os.path.exists(path):
            continue
        root = path if os.path.isdir(path) else os.path.dirname(path)
        if root not in seen and os.path.exists(os.path.join(root, "Dockerfile")):
            seen.add(root)
            yield root


def collect_backend_weights(plugin_dirs, explicit_plugins=(), fallback_names=None):
    """Build the ``backend_name -> weight`` map from on-disk manifests.

    ``fallback_names`` maps a plugin directory to the backend name discovered by
    the decorator scan, so a manifest that omits ``name`` still lands under the
    right key."""
    weights = {}
    for root in iter_plugin_dirs(plugin_dirs, explicit_plugins):
        manifest = read_manifest(root)
        if not manifest:
            continue
        weight = manifest_weight(manifest)
        if weight is None:
            continue
        name = manifest.get("name") or (fallback_names or {}).get(root) or os.path.basename(root)
        weights[str(name)] = weight
    return weights
