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


def load_config(
    *,
    browser: str,
    caps: str,
    config_path: Path | None,
    headless: bool,
    test_id_attribute: str,
    vision: bool,
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
    )
