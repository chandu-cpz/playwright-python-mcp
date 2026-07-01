from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ServerConfig:
    browser: str = "chrome"
    caps: set[str] | None = None
    headless: bool = False
    allow_unrestricted_file_access: bool = False
    test_id_attribute: str = "data-testid"
    codegen: str = "python"
    console_level: str = "info"
    image_responses: str = "allow"
    output_dir: Path | None = None
    output_max_size: int | None = None
    output_mode: str = "file"
    secrets: dict[str, str] | None = None
    snapshot_mode: str = "full"


def load_config(
    *,
    browser: str,
    caps: str,
    config_path: Path | None,
    headless: bool,
    test_id_attribute: str,
    vision: bool,
    console_level: str | None = None,
) -> ServerConfig:
    loaded = {}
    if config_path is not None:
        loaded = json.loads(config_path.read_text())

    merged_caps = set(loaded.get("capabilities", []))
    merged_caps.update(part.strip() for part in caps.split(",") if part.strip())
    if vision:
        merged_caps.add("vision")

    return ServerConfig(
        browser=browser,
        caps=merged_caps,
        headless=headless,
        allow_unrestricted_file_access=bool(loaded.get("allowUnrestrictedFileAccess", False)),
        test_id_attribute=str(loaded.get("testIdAttribute", test_id_attribute)),
        codegen=str(loaded.get("codegen", "python")),
        console_level=console_level or str(loaded.get("console", {}).get("level", "info")),
        image_responses=str(loaded.get("imageResponses", "allow")),
        output_dir=Path(loaded["outputDir"]) if loaded.get("outputDir") else None,
        output_max_size=loaded.get("outputMaxSize"),
        output_mode=str(loaded.get("outputMode", "file")),
        secrets=loaded.get("secrets"),
        snapshot_mode=str(loaded.get("snapshot", {}).get("mode", "full")),
    )
