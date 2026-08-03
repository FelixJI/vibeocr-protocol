"""Build the immutable project and Protocol identity release asset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_identity(
    *, output: Path, version: str, source_sha: str, openapi: Path
) -> Path:
    value = {
        "schema_version": 1,
        "project": {
            "component": "protocol",
            "repository": "FelixJI/vibeocr-protocol",
            "version": version,
            "source_sha": source_sha,
        },
        "protocol": {
            "version": version,
            "source": {
                "repository": "FelixJI/vibeocr-protocol",
                "sha": source_sha,
            },
            "contract": {"name": openapi.name, "sha256": _sha256(openapi)},
            "compatibility": {"supported_majors": [2], "minor_compatible": True},
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--openapi", type=Path, required=True)
    args = parser.parse_args()
    print(build_identity(**vars(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
