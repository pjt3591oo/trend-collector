"""Load secrets beside the selected config, preserving exported environment values."""
from pathlib import Path
import os
import re
import tomllib
from dotenv import load_dotenv


def load_environment(config_path=None):
    folder = Path(config_path).resolve().parent if config_path else Path.cwd()
    load_dotenv(folder / '.env', override=False, encoding='utf-8-sig', interpolate=False)


def load_config(config_path=None, *, optional=False, sections=None, resolve=True):
    """Parse TOML first, then substitute ${NAME} in string values without re-parsing secrets."""
    load_environment(config_path)
    if config_path is None:
        return {}
    path = Path(config_path)
    if optional and not path.exists():
        return {}
    config = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    if sections is not None:
        config = {key: value for key, value in config.items() if key in sections}
    return resolve_settings(config) if resolve else config


def resolve_settings(value):
    def resolve(value):
        if isinstance(value, dict):
            if value.get("enabled") is False:
                return value.copy()
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, str):
            def substitute(match):
                name = match[1]
                if name not in os.environ:
                    raise ValueError(f'환경 변수가 없습니다: {name} (.env를 확인하세요)')
                return os.environ[name]
            return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', substitute, value)
        return value
    return resolve(value)


def load_application_config(path, *, optional=False):
    """Resolve ordinary settings now, credentials only when their feature is invoked."""
    config = load_config(path, optional=optional, resolve=False, sections=('collector', 'publishing', 'channels'))
    channels = config.pop('channels', {})
    publishing = config.get('publishing', {}).copy()
    llm = publishing.pop('llm', {})
    if 'publishing' in config:
        config['publishing'] = publishing
    config = resolve_settings(config)
    config['channels'] = channels
    config.setdefault('publishing', {})['llm'] = llm
    return config
