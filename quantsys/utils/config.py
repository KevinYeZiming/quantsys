"""YAML configuration loader with environment variable interpolation."""

import os
import re
from pathlib import Path
from typing import Any

import yaml


def _interpolate_env(value: Any) -> Any:
    """Recursively interpolate ${ENV_VAR} patterns in config values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")
        matches = pattern.findall(value)
        for match in matches:
            env_val = os.environ.get(match, "")
            value = value.replace(f"${{{match}}}", env_val)
        return value
    elif isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


def load_config(config_path: str | Path) -> dict:
    """Load a YAML configuration file with environment variable interpolation.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Parsed configuration dictionary.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if config is None:
        return {}

    return _interpolate_env(config)


def load_all_configs(config_dir: str | Path = None) -> dict:
    """Load all YAML configuration files from the config directory.

    Args:
        config_dir: Path to the config directory. Defaults to 'config/' relative to project root.

    Returns:
        Dictionary mapping config name (filename without extension) to config dict.
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent / "config"
    else:
        config_dir = Path(config_dir)

    configs = {}
    for config_file in sorted(config_dir.glob("*.yaml")):
        if config_file.name.startswith("._"):
            continue
        name = config_file.stem
        configs[name] = load_config(config_file)

    return configs
