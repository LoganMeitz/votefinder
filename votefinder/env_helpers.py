# This is a helper module for reading Django settings from the operating system's environment and/or a local dotenv,
# and converting them to typed values.
import os
from dotenv import load_dotenv


# Load extra environment from .env, if present.
load_dotenv()


def env_bool(name: str, default=False):
    """Retrieves a value from the environment and converts it to a boolean.

    Values of "true", "yes" or "1" are interpreted as true, values of "false", "no" or "0" are interpreted as false.
    Anything else returns the default value. Values are case insensitive.
    """
    if name not in os.environ:
        return default
    else:
        value = os.environ[name].lower()

        if value in ["true", "yes", "1"]:
            return True
        elif value in ["false", "no", "0"]:
            return False
        else:
            return default


def env_string(name: str, default=None):
    """Retrieves a string value from the environment."""
    return os.environ.get(name, default)


def env_integer(name: str, default=None):
    """Retrieves a value from the environment and converts it to an integer."""
    if name not in os.environ:
        return default
    else:
        try:
            return int(os.environ[name])
        except ValueError:
            return default


def env_float(name: str, default=None):
    """Retrieves a value from the environment and converts it to a floating point number."""
    if name not in os.environ:
        return default
    else:
        try:
            return float(os.environ[name])
        except ValueError:
            return default


def env_string_list(name: str, separator: str = ' ', default=None):
    """Retrieves a value from the environment and splits it into a list of strings."""
    default = default or []

    if name not in os.environ:
        return default
    else:
        return os.environ[name].split(separator)


__all__ = ['env_bool', 'env_string', 'env_integer', 'env_float', 'env_string_list']
