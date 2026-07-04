from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "browser": {
        "launchOptions": {},
        "contextOptions": {},
    },
    "timeouts": {
        "action": 5000,
        "navigation": 60000,
        "expect": 5000,
    },
    "codegen": "python",
    "console": {
        "level": "info",
    },
    "imageResponses": "allow",
    "outputMode": "file",
    "snapshot": {
        "mode": "full",
    },
    "testIdAttribute": "data-testid",
}


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
    save_session: bool = False
    shared_browser_context: bool = False
    secrets: dict[str, str] | None = None
    snapshot_mode: str = "full"
    action_timeout: int | None = 5000
    navigation_timeout: int | None = 60000
    expect_timeout: int | None = 5000
    public_config: dict[str, Any] = field(default_factory=dict)
    browser_name: str = "chromium"
    browser_channel: str | None = "chrome"
    browser_launch_options: dict[str, Any] = field(default_factory=dict)
    browser_context_options: dict[str, Any] = field(default_factory=dict)
    browser_isolated: bool | None = None
    browser_user_data_dir: Path | None = None
    cdp_endpoint: str | None = None
    cdp_headers: dict[str, str] | None = None
    cdp_timeout: int | None = None
    remote_endpoint: str | dict[str, Any] | None = None
    remote_headers: dict[str, str] | None = None
    init_scripts: list[Path] = field(default_factory=list)
    init_pages: list[Path] = field(default_factory=list)
    allowed_origins: list[str] = field(default_factory=list)
    blocked_origins: list[str] = field(default_factory=list)
    extension: bool = False
    server_host: str | None = None
    server_port: int | None = None
    allowed_hosts: list[str] | None = None
    config_file: str | None = None

    def as_public_dict(self) -> dict[str, Any]:
        return _jsonable(self.public_config)


def load_config(
    *,
    browser: str | None,
    caps: str | list[str] | None,
    config_path: Path | None,
    headless: bool | None,
    test_id_attribute: str | None,
    vision: bool,
    console_level: str | None = None,
    output_dir: Path | None = None,
    **cli_options: Any,
) -> ServerConfig:
    env_config = _config_from_env(os.environ)
    cli_config = _config_from_cli(
        browser=browser,
        caps=caps,
        headless=headless,
        test_id_attribute=test_id_attribute,
        vision=vision,
        console_level=console_level,
        output_dir=output_dir,
        **cli_options,
    )
    config_file = config_path or (Path(env_config["configFile"]) if env_config.get("configFile") else None)
    file_config = _load_config_file(config_file) if config_file else {}
    config_dir = config_file.resolve().parent if config_file else Path.cwd()

    merged = _merge_config(DEFAULT_CONFIG, _resolve_config_paths(file_config, config_dir))
    merged = _merge_config(merged, _resolve_config_paths(env_config, Path.cwd()))
    merged = _merge_config(merged, _resolve_config_paths(cli_config, Path.cwd()))
    merged["configFile"] = str(config_file) if config_file else None
    _validate_and_complete(merged)
    return _server_config_from_merged(merged)


def resolve_config(user_config: dict[str, Any] | ServerConfig | None = None) -> ServerConfig:
    if isinstance(user_config, ServerConfig):
        return user_config
    merged = _merge_config(DEFAULT_CONFIG, user_config or {})
    _validate_and_complete(merged)
    return _server_config_from_merged(merged)


def _config_from_cli(
    *,
    browser: str | None,
    caps: str | list[str] | None,
    headless: bool | None,
    test_id_attribute: str | None,
    vision: bool,
    console_level: str | None,
    output_dir: Path | None,
    **options: Any,
) -> dict[str, Any]:
    browser_name, channel = _resolve_browser_param(browser)
    launch_options: dict[str, Any] = {
        "channel": channel,
        "executablePath": options.get("executable_path"),
        "headless": headless,
    }
    if options.get("sandbox") is not None:
        launch_options["chromiumSandbox"] = options["sandbox"]

    context_options: dict[str, Any] = {}
    if options.get("proxy_server"):
        proxy = {"server": options["proxy_server"]}
        if options.get("proxy_bypass"):
            proxy["bypass"] = options["proxy_bypass"]
        launch_options["proxy"] = proxy
        context_options["proxy"] = proxy
    if options.get("storage_state"):
        context_options["storageState"] = options["storage_state"]
    if options.get("user_agent"):
        context_options["userAgent"] = options["user_agent"]
    if options.get("viewport_size"):
        context_options["viewport"] = options["viewport_size"]
    if options.get("ignore_https_errors"):
        context_options["ignoreHTTPSErrors"] = True
    if options.get("block_service_workers"):
        context_options["serviceWorkers"] = "block"
    if options.get("grant_permissions"):
        context_options["permissions"] = options["grant_permissions"]

    cap_list = _capabilities(caps)
    if vision:
        cap_list.append("vision")
    if "tracing" in cap_list and "devtools" not in cap_list:
        cap_list.append("devtools")

    return _strip_undefined(
        {
            "browser": _strip_undefined(
                {
                    "browserName": browser_name,
                    "isolated": options.get("isolated"),
                    "userDataDir": str(options["user_data_dir"]) if options.get("user_data_dir") else None,
                    "launchOptions": _strip_undefined(launch_options),
                    "contextOptions": _strip_undefined(context_options),
                    "cdpEndpoint": options.get("cdp_endpoint"),
                    "cdpHeaders": options.get("cdp_header"),
                    "cdpTimeout": options.get("cdp_timeout"),
                    "initPage": options.get("init_page"),
                    "initScript": options.get("init_script"),
                    "remoteEndpoint": options.get("endpoint"),
                    "remoteHeaders": options.get("remote_header"),
                }
            ),
            "extension": options.get("extension"),
            "server": _strip_undefined(
                {"port": options.get("port"), "host": options.get("host"), "allowedHosts": options.get("allowed_hosts")}
            ),
            "capabilities": cap_list or None,
            "console": _strip_undefined({"level": console_level}),
            "network": _strip_undefined(
                {"allowedOrigins": options.get("allowed_origins"), "blockedOrigins": options.get("blocked_origins")}
            ),
            "allowUnrestrictedFileAccess": options.get("allow_unrestricted_file_access"),
            "codegen": options.get("codegen"),
            "saveSession": options.get("save_session"),
            "secrets": options.get("secrets"),
            "sharedBrowserContext": options.get("shared_browser_context"),
            "snapshot": _strip_undefined({"mode": options.get("snapshot_mode")}),
            "outputDir": str(output_dir) if output_dir else None,
            "outputMaxSize": options.get("output_max_size"),
            "outputMode": options.get("output_mode"),
            "imageResponses": options.get("image_responses"),
            "testIdAttribute": test_id_attribute,
            "timeouts": _strip_undefined(
                {
                    "action": options.get("timeout_action") or options.get("timeout"),
                    "navigation": options.get("timeout_navigation"),
                }
            ),
        }
    )


def _config_from_env(env: os._Environ[str]) -> dict[str, Any]:
    return _config_from_cli(
        browser=_env_string(env, "PLAYWRIGHT_MCP_BROWSER"),
        caps=_env_list(env, "PLAYWRIGHT_MCP_CAPS"),
        headless=_env_bool(env, "PLAYWRIGHT_MCP_HEADLESS"),
        test_id_attribute=_env_string(env, "PLAYWRIGHT_MCP_TEST_ID_ATTRIBUTE"),
        vision=False,
        console_level=_env_string(env, "PLAYWRIGHT_MCP_CONSOLE_LEVEL"),
        output_dir=Path(env["PLAYWRIGHT_MCP_OUTPUT_DIR"]) if _env_string(env, "PLAYWRIGHT_MCP_OUTPUT_DIR") else None,
        allowed_hosts=_env_list(env, "PLAYWRIGHT_MCP_ALLOWED_HOSTS"),
        allowed_origins=_env_semicolon_list(env, "PLAYWRIGHT_MCP_ALLOWED_ORIGINS"),
        allow_unrestricted_file_access=_env_bool(env, "PLAYWRIGHT_MCP_ALLOW_UNRESTRICTED_FILE_ACCESS"),
        blocked_origins=_env_semicolon_list(env, "PLAYWRIGHT_MCP_BLOCKED_ORIGINS"),
        block_service_workers=_env_bool(env, "PLAYWRIGHT_MCP_BLOCK_SERVICE_WORKERS"),
        cdp_endpoint=_env_string(env, "PLAYWRIGHT_MCP_CDP_ENDPOINT"),
        cdp_header=_headers(env.get("PLAYWRIGHT_MCP_CDP_HEADERS")),
        cdp_timeout=_env_int(env, "PLAYWRIGHT_MCP_CDP_TIMEOUT"),
        codegen=_env_string(env, "PLAYWRIGHT_MCP_CODEGEN"),
        executable_path=_env_string(env, "PLAYWRIGHT_MCP_EXECUTABLE_PATH"),
        extension=_env_bool(env, "PLAYWRIGHT_MCP_EXTENSION"),
        grant_permissions=_env_list(env, "PLAYWRIGHT_MCP_GRANT_PERMISSIONS"),
        host=_env_string(env, "PLAYWRIGHT_MCP_HOST"),
        ignore_https_errors=_env_bool(env, "PLAYWRIGHT_MCP_IGNORE_HTTPS_ERRORS"),
        init_page=[value] if (value := _env_string(env, "PLAYWRIGHT_MCP_INIT_PAGE")) else None,
        init_script=[value] if (value := _env_string(env, "PLAYWRIGHT_MCP_INIT_SCRIPT")) else None,
        isolated=_env_bool(env, "PLAYWRIGHT_MCP_ISOLATED"),
        image_responses=_env_string(env, "PLAYWRIGHT_MCP_IMAGE_RESPONSES"),
        sandbox=_env_bool(env, "PLAYWRIGHT_MCP_SANDBOX"),
        shared_browser_context=_env_bool(env, "PLAYWRIGHT_MCP_SHARED_BROWSER_CONTEXT"),
        output_max_size=_env_int(env, "PLAYWRIGHT_MCP_OUTPUT_MAX_SIZE"),
        output_mode=_env_string(env, "PLAYWRIGHT_MCP_OUTPUT_MODE"),
        port=_env_int(env, "PLAYWRIGHT_MCP_PORT"),
        proxy_bypass=_env_string(env, "PLAYWRIGHT_MCP_PROXY_BYPASS"),
        proxy_server=_env_string(env, "PLAYWRIGHT_MCP_PROXY_SERVER"),
        secrets=_dotenv(Path(value)) if (value := _env_string(env, "PLAYWRIGHT_MCP_SECRETS_FILE")) else None,
        storage_state=_env_string(env, "PLAYWRIGHT_MCP_STORAGE_STATE"),
        timeout_action=_env_int(env, "PLAYWRIGHT_MCP_TIMEOUT_ACTION"),
        timeout_navigation=_env_int(env, "PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION"),
        user_agent=_env_string(env, "PLAYWRIGHT_MCP_USER_AGENT"),
        user_data_dir=_env_string(env, "PLAYWRIGHT_MCP_USER_DATA_DIR"),
        viewport_size=_resolution(_env_string(env, "PLAYWRIGHT_MCP_VIEWPORT_SIZE")),
    ) | {"configFile": _env_string(env, "PLAYWRIGHT_MCP_CONFIG")}


def _load_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".ini":
        return _config_from_ini(text)
    try:
        return json.loads(text.lstrip("\ufeff"))
    except json.JSONDecodeError:
        return _config_from_ini(text)


def _config_from_ini(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        _set_dotted(result, key, _parse_ini_value(key, value))
    return result


def _parse_ini_value(key: str, value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if key == "capabilities":
        return [item.strip() for item in value.split(",") if item.strip()]
    if key.endswith(("initScript", "initPage")):
        return [item.strip() for item in value.split(";") if item.strip()]
    if key.endswith(("allowedOrigins", "blockedOrigins")):
        return [item.strip() for item in value.split(";") if item.strip()]
    if key.endswith("viewport"):
        return _resolution(value)
    if value.isdigit():
        return int(value)
    return value


def _validate_and_complete(config: dict[str, Any]) -> None:
    browser = config.setdefault("browser", {})
    launch_options = browser.setdefault("launchOptions", {})
    context_options = browser.setdefault("contextOptions", {})
    if browser.get("isolated") and browser.get("userDataDir"):
        raise ValueError("Browser userDataDir is not supported in isolated mode.")
    browser_name, default_channel = _resolve_browser_param(None)
    browser["browserName"] = browser.get("browserName") or browser_name
    if launch_options.get("channel") is None and browser.get("browserName") == "chromium":
        launch_options["channel"] = default_channel
    if launch_options.get("headless") is None:
        launch_options["headless"] = os.name == "posix" and not os.environ.get("DISPLAY")
    if browser.get("browserName") == "chromium":
        channel = launch_options.get("channel")
        if launch_options.get("chromiumSandbox") is None:
            launch_options["chromiumSandbox"] = (
                os.name != "posix"
                or channel not in {"chromium", "chrome-for-testing"}
            )
        args = list(launch_options.get("args") or [])
        if not any(str(arg).startswith("--disable-blink-features") for arg in args):
            args.append("--disable-blink-features=AutomationControlled")
        launch_options["args"] = args
    if context_options.get("viewport") is None:
        context_options["viewport"] = {"width": 1280, "height": 720} if launch_options.get("headless") else None
    console = config.setdefault("console", {})
    if console.get("level") not in {None, "error", "warning", "info", "debug"}:
        raise ValueError('console.level must be one of "error", "warning", "info", "debug"')
    if config.get("outputMode") not in {None, "file", "stdout"}:
        raise ValueError('outputMode must be one of "file" or "stdout"')
    if config.get("outputDir") and _is_system_directory(Path(config["outputDir"])):
        raise ValueError(f'outputDir must not be a system directory: {config["outputDir"]}')


def _server_config_from_merged(config: dict[str, Any]) -> ServerConfig:
    browser = config.get("browser", {})
    launch_options = browser.get("launchOptions", {})
    context_options = browser.get("contextOptions", {})
    timeouts = config.get("timeouts", {})
    console = config.get("console", {})
    snapshot = config.get("snapshot", {})
    server = config.get("server", {})
    caps = set(config.get("capabilities") or [])
    return ServerConfig(
        browser=launch_options.get("channel") or browser.get("browserName") or "chromium",
        caps=caps,
        headless=bool(launch_options.get("headless")),
        allow_unrestricted_file_access=bool(config.get("allowUnrestrictedFileAccess", False)),
        test_id_attribute=str(config.get("testIdAttribute") or "data-testid"),
        codegen=str(config.get("codegen") or "python"),
        console_level=str(console.get("level") or "info"),
        image_responses=str(config.get("imageResponses") or "allow"),
        output_dir=Path(config["outputDir"]) if config.get("outputDir") else None,
        output_max_size=config.get("outputMaxSize"),
        output_mode=str(config.get("outputMode") or "file"),
        save_session=bool(config.get("saveSession", False)),
        shared_browser_context=bool(config.get("sharedBrowserContext", False)),
        secrets=config.get("secrets"),
        snapshot_mode=str(snapshot.get("mode") or "full"),
        action_timeout=timeouts.get("action"),
        navigation_timeout=timeouts.get("navigation"),
        expect_timeout=timeouts.get("expect"),
        public_config=config,
        browser_name=str(browser.get("browserName") or "chromium"),
        browser_channel=launch_options.get("channel"),
        browser_launch_options=_to_python_launch_options(launch_options),
        browser_context_options=_to_python_context_options(context_options),
        browser_isolated=browser.get("isolated"),
        browser_user_data_dir=Path(browser["userDataDir"]) if browser.get("userDataDir") else None,
        cdp_endpoint=browser.get("cdpEndpoint"),
        cdp_headers=browser.get("cdpHeaders"),
        cdp_timeout=browser.get("cdpTimeout"),
        remote_endpoint=browser.get("remoteEndpoint"),
        remote_headers=browser.get("remoteHeaders"),
        init_scripts=[Path(value) for value in browser.get("initScript", [])],
        init_pages=[Path(value) for value in browser.get("initPage", [])],
        allowed_origins=list(config.get("network", {}).get("allowedOrigins") or []),
        blocked_origins=list(config.get("network", {}).get("blockedOrigins") or []),
        extension=bool(config.get("extension", False)),
        server_host=server.get("host"),
        server_port=server.get("port"),
        allowed_hosts=server.get("allowedHosts"),
        config_file=config.get("configFile"),
    )


def _to_python_launch_options(options: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "channel": "channel",
        "executablePath": "executable_path",
        "headless": "headless",
        "chromiumSandbox": "chromium_sandbox",
        "proxy": "proxy",
        "args": "args",
        "ignoreDefaultArgs": "ignore_default_args",
        "handleSIGINT": "handle_sigint",
        "handleSIGTERM": "handle_sigterm",
        "handleSIGHUP": "handle_sighup",
        "tracesDir": "traces_dir",
        "artifactsDir": "artifacts_dir",
    }
    return {mapping[key]: value for key, value in options.items() if key in mapping and value is not None}


def _to_python_context_options(options: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "viewport": "viewport",
        "proxy": "proxy",
        "storageState": "storage_state",
        "userAgent": "user_agent",
        "ignoreHTTPSErrors": "ignore_https_errors",
        "serviceWorkers": "service_workers",
        "permissions": "permissions",
        "locale": "locale",
        "timezoneId": "timezone_id",
        "bypassCSP": "bypass_csp",
        "javaScriptEnabled": "java_script_enabled",
    }
    return {mapping[key]: value for key, value in options.items() if key in mapping and value is not None}


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(_jsonable(base)))
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_config_paths(config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    browser = config.get("browser")
    if not isinstance(browser, dict):
        return config
    for key in ("initPage", "initScript"):
        values = browser.get(key)
        if values:
            browser[key] = [str((base_dir / value).resolve()) for value in values]
    return config


def _resolve_browser_param(browser: str | None) -> tuple[str | None, str | None]:
    if browser in {"chrome", "chrome-beta", "chrome-canary", "chrome-dev", "msedge", "msedge-beta", "msedge-canary", "msedge-dev"}:
        return "chromium", browser
    if browser == "chromium":
        return "chromium", "chrome-for-testing"
    if browser in {"firefox", "webkit"}:
        return browser, None
    if browser in {"moz-firefox", "moz-firefox-beta", "moz-firefox-nightly"}:
        return "firefox", browser
    if browser is None:
        return "chromium", "chrome"
    return None, None


def _strip_undefined(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None and item != {}}


def _set_dotted(target: dict[str, Any], key: str, value: Any) -> None:
    current = target
    parts = key.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _capabilities(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [item.strip() for item in value if item.strip()]


def _env_string(env: os._Environ[str], key: str) -> str | None:
    value = env.get(key)
    return value.strip() if value else None


def _env_bool(env: os._Environ[str], key: str) -> bool | None:
    value = env.get(key)
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    return None


def _env_int(env: os._Environ[str], key: str) -> int | None:
    value = env.get(key)
    return int(value) if value else None


def _env_list(env: os._Environ[str], key: str) -> list[str] | None:
    value = env.get(key)
    return [item.strip() for item in value.split(",") if item.strip()] if value else None


def _env_semicolon_list(env: os._Environ[str], key: str) -> list[str] | None:
    value = env.get(key)
    return [item.strip() for item in value.split(";") if item.strip()] if value else None


def _headers(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    result: dict[str, str] = {}
    for header in value.split(","):
        name, _, header_value = header.partition(":")
        result[name.strip()] = header_value.strip()
    return result


def _resolution(value: str | None) -> dict[str, int] | None:
    if not value:
        return None
    delimiter = "x" if "x" in value else ","
    width, height = (int(part) for part in value.split(delimiter, 1))
    return {"width": width, "height": height}


def _is_system_directory(path: Path) -> bool:
    resolved = path.resolve()
    return resolved in {Path("/"), Path("/tmp"), Path("/var"), Path("/usr"), Path("/bin"), Path("/etc")}


def _dotenv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value
