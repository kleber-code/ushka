## `module`

```python
This module defines custom HTTP exception classes for the Ushka framework.

These exceptions correspond to specific HTTP status codes and are used to
interrupt the normal request flow and return an appropriate error response
to the client.
```

## `HTTPError`

```python
Base class for all HTTP-related exceptions in Ushka.

Attributes:
    status_code (int): The HTTP status code associated with the error.
    template (str): The name of the template to use for rendering the
        error page.
    message (str): A descriptive error message.
```

## `HttpNotFound`

```python
Raised when a requested resource could not be found (HTTP 404).
```

## `HttpStaticServerNotFound`

```python
Raised when a requested static file could not be found (HTTP 404).

This is a specialized version of `HttpNotFound` for use in the static
file server.
```

