## `module`

```python
This module defines the `Response` class for handling HTTP responses.

The `Response` class is a core component of the Ushka framework, providing a
flexible and easy-to-use interface for constructing HTTP responses. It supports
various content types, including HTML, JSON, and binary data, and ensures
correct formatting for ASGI compatibility.
```

## `Response`

```python
Represents an outgoing HTTP response.

This class manages the response body, status code, headers, and media type.
It can handle content as strings, bytes, dictionaries, or lists,
automatically setting the appropriate `Content-Type` header and encoding
the body for transmission.

Attributes:
    status_code (int): The HTTP status code.
    headers (dict): A dictionary of response headers.
    media_type (str): The MIME type of the response.
```

## `Response.body`

```python
Sets the response body.

This setter handles different types of content:
- `bytes`: Stored directly for binary responses.
- `str`: Stored as a string. `media_type` is inferred.
- `dict` or `list`: Serialized to a JSON string.

Raises:
    ContentToJsonParserFailed: If serialization of a dict or list
        to JSON fails.
```

