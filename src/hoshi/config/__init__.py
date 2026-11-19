"""配置包。"""

from .loader import Config, ConfigError, Entry, default_path, load, save
from .schema import BY_KEY, SCHEMA, Item, groups

__all__ = [
    "BY_KEY",
    "SCHEMA",
    "Config",
    "ConfigError",
    "Entry",
    "Item",
    "default_path",
    "groups",
    "load",
    "save",
]
