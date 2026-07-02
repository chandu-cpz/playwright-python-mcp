from __future__ import annotations

from pathlib import Path

from playwright_python_mcp.mcp.config import load_config


def test_cli_overrides_env_and_file(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text('{"timeouts": {"action": 1000, "navigation": 2000}, "browser": {"browserName": "firefox"}}')
    monkeypatch.setenv("PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION", "45000")
    monkeypatch.setenv("PLAYWRIGHT_MCP_BROWSER", "webkit")

    config = load_config(
        browser="chromium",
        caps="config",
        config_path=config_file,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        timeout_action=9999,
    )

    public = config.as_public_dict()
    assert public["timeouts"]["action"] == 9999
    assert public["timeouts"]["navigation"] == 45000
    assert public["browser"]["browserName"] == "chromium"
    assert public["browser"]["launchOptions"]["channel"] == "chrome-for-testing"


def test_ini_config_resolution(tmp_path: Path) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
        capabilities = config,storage
        console.level = error
        timeouts.action = 12345
        browser.contextOptions.viewport = 640x480
        browser.contextOptions.bypassCSP = true
        """
    )

    config = load_config(
        browser=None,
        caps="",
        config_path=config_file,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    public = config.as_public_dict()
    assert public["capabilities"] == ["config", "storage"]
    assert public["console"]["level"] == "error"
    assert public["timeouts"]["action"] == 12345
    assert public["browser"]["contextOptions"]["viewport"] == {"width": 640, "height": 480}
    assert public["browser"]["contextOptions"]["bypassCSP"] is True


def test_remote_endpoint_headers_are_preserved() -> None:
    config = load_config(
        browser=None,
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        endpoint="ws://example.invalid",
        remote_header={"Authorization": "Bearer token"},
    )

    assert config.remote_endpoint == "ws://example.invalid"
    assert config.remote_headers == {"Authorization": "Bearer token"}
    assert config.as_public_dict()["browser"]["remoteHeaders"] == {"Authorization": "Bearer token"}
