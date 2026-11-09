"""Apply the bounded REPL facade addition to the exact pinned Serena source.

Run only in the owned candidate installation after uv sync. Source and patch
hashes are checked before mutation; a second invocation is idempotent.
"""
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess

SERENA_SOURCE = "9e1cced0c34ed48d668e179f7c56c77b4d14a3e3"
BASE_SHA256 = "c95adadaf1e55a5b310a2fb43330143d53da9c62cef704ce5b342d126ee14cef"
CANDIDATE_SHA256 = "438e52fc79044efa5264e84638190a68a5d5be4ed18f9e2f698f7a49e10d184e"
PATCH_SHA256 = "57385a9e49d8a490e696f49b3c62d16e8685703d9531899372a3c41a28270051"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply(site_root):
    site_root = Path(site_root).resolve()
    target = site_root / "serena/repl/api/lsp_api.py"
    patch = Path(__file__).with_name("serena-symbol-references.patch").resolve()
    if digest(patch) != PATCH_SHA256:
        raise RuntimeError("Serena facade patch digest does not match the reviewed candidate")
    current = digest(target)
    if current == CANDIDATE_SHA256:
        return target
    if current != BASE_SHA256:
        raise RuntimeError("Serena facade source does not match the exact pinned base")
    command = ["git", "apply", "--whitespace=error", str(patch)]
    subprocess.run([*command[:2], "--check", *command[2:]], cwd=site_root, check=True)
    subprocess.run(command, cwd=site_root, check=True)
    if digest(target) != CANDIDATE_SHA256:
        raise RuntimeError("Patched Serena facade does not match the reviewed candidate")
    return target


def main():
    import serena
    direct_url = json.loads(distribution("serena-agent").read_text("direct_url.json"))
    if direct_url.get("vcs_info", {}).get("commit_id") != SERENA_SOURCE:
        raise RuntimeError("Serena installed source revision differs from the reviewed base")
    target = apply(Path(serena.__file__).resolve().parent.parent)
    print(json.dumps({"source": SERENA_SOURCE, "patch_sha256": PATCH_SHA256,
                      "installed_lsp_api_sha256": digest(target)}))


if __name__ == "__main__":
    main()
