## `module`

```python
This module provides logging configuration for the Ushka framework.

It sets up a visually appealing and informative logging system using the `rich`
library. It includes a custom `RichHandler` for console output and provides
a method to configure Uvicorn for silent logging, ensuring that all output
is consistently formatted.
```

## `LogSystem`

```python
Manages the logging system for the Ushka framework.

This class configures the 'ushka' logger with a custom `UshkaHandler` to
provide rich, formatted console output.
```

## `LogSystem.log_http`

```python
Logs an HTTP request/response cycle.

Formats the log message with icons and colors based on the response
status code.

Args:
    request: The incoming `Request` object.
    response: The outgoing `Response` object.
    process_time: The total time taken to process the request, in
        milliseconds.
```

## `LogSystem.get_silent_uvicorn_config`

```python
Gets a logging configuration to silence default Uvicorn loggers.

This method returns a dictionary that can be passed to `uvicorn.run`
to route Uvicorn's logs through Ushka's custom handler, ensuring
consistent log formatting.

Args:
    level: The desired logging level for the 'ushka' logger.

Returns:
    A dictionary containing the logging configuration for Uvicorn.
```

## `UshkaHandler`

```python
Custom `RichHandler` for Ushka logging.

This class extends `rich.logging.RichHandler` to ensure a consistent
look and feel for all framework and application logs.
```

## `log_http`

```python
Logs an HTTP request/response cycle.

Formats the log message with icons and colors based on the response
status code.

Args:
    request: The incoming `Request` object.
    response: The outgoing `Response` object.
    process_time: The total time taken to process the request, in
        milliseconds.
```

## `get_silent_uvicorn_config`

```python
Gets a logging configuration to silence default Uvicorn loggers.

This method returns a dictionary that can be passed to `uvicorn.run`
to route Uvicorn's logs through Ushka's custom handler, ensuring
consistent log formatting.

Args:
    level: The desired logging level for the 'ushka' logger.

Returns:
    A dictionary containing the logging configuration for Uvicorn.
```

