from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_release_identity import build_identity


def test_build_identity_binds_project_protocol_source_and_contract(
    tmp_path: Path,
) -> None:
    openapi = tmp_path / "vibeocr-runtime-openapi-2.1.0.yaml"
    openapi.write_text('{"info":{"version":"2.1.0"}}\n', encoding="utf-8")

    output = build_identity(
        output=tmp_path / "build-identity.json",
        version="2.1.0",
        source_sha="a" * 40,
        openapi=openapi,
    )

    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["project"] == {
        "component": "protocol",
        "repository": "FelixJI/vibeocr-protocol",
        "version": "2.1.0",
        "source_sha": "a" * 40,
    }
    assert value["protocol"]["source"]["sha"] == "a" * 40
    assert value["protocol"]["contract"] == {
        "name": openapi.name,
        "sha256": hashlib.sha256(openapi.read_bytes()).hexdigest(),
    }
