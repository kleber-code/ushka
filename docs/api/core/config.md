## `module`

```python
This module handles configuration management for the Ushka framework.

It defines the `Config` class, which uses a Singleton pattern to provide
global access to application settings. Configuration is loaded from an
'ushka.toml' file, with support for default values and automatic file
generation.
```

## `Config`

```python
Manages application configuration using a Singleton pattern.

This class loads settings from an 'ushka.toml' file, provides default
values for missing keys, and makes configuration accessible throughout the
application. The Singleton implementation ensures that there is only one
instance of the configuration object.

Attributes are dynamically set from the TOML file in the format
`SECTION_KEY` (e.g., `APP_DEBUG`).
```

## `Config.load_from_file`

```python
Loads configuration from a TOML file.

If the specified file does not exist, it creates one with default
settings. It merges existing settings with defaults to ensure all
necessary configuration keys are present.

Args:
    config_path: The path to the 'ushka.toml' configuration file.

Returns:
    The loaded and merged configuration as a TOML document object.
```

## `Config.get`

```python
Retrieves a configuration value by its attribute name.

Args:
    key: The name of the configuration attribute (e.g., 'APP_DEBUG').
    default: The value to return if the key is not found.

Returns:
    The configuration value or the specified default.
```

