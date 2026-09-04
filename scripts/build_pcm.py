from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "build" / "pcm"
DIST = ROOT / "dist"
VERSION = "0.1.0"


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def main() -> int:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)

    shutil.copy2(ROOT / "pcm" / "metadata.json", STAGE / "metadata.json")
    copy_tree(ROOT / "pcm" / "resources", STAGE / "resources")
    copy_tree(ROOT / "pcm" / "plugins", STAGE / "plugins")
    copy_tree(ROOT / "partharbor", STAGE / "plugins" / "partharbor")
    copy_tree(ROOT / "easyeda2kicad", STAGE / "plugins" / "easyeda2kicad")
    shutil.copy2(ROOT / "LICENSE", STAGE / "plugins" / "LICENSE")

    archive = DIST / f"partharbor-{VERSION}-pcm.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(STAGE).as_posix())

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    details = {
        "archive": str(archive),
        "sha256": digest,
        "download_size": archive.stat().st_size,
        "install_size": sum(path.stat().st_size for path in STAGE.rglob("*") if path.is_file()),
    }
    print(json.dumps(details, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
