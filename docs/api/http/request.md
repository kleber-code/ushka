## `module`

```python
This module defines the `Request` class for handling incoming HTTP requests.

The `Request` class encapsulates the ASGI scope and receive stream, providing a
convenient, high-level interface for accessing request details such as
headers, query parameters, and the request body in various formats (e.g.,
bytes, text, JSON, form data).
```

## `Request`

```python
Represents an incoming HTTP request.

This class provides convenient access to request attributes like headers,
query parameters, and the body. It lazily loads and caches properties to
avoid redundant processing.

Attributes:
    scope (dict): The raw ASGI scope dictionary.
    method (str): The HTTP method of the request (e.g., 'GET', 'POST').
    path (str): The URL path of the request.
```

## `Request.headers`

```python
The request headers as a case-insensitive dictionary.
```

## `Request.query`

```python
The parsed query parameters from the URL as a dictionary.
```

## `Request.body`

```python
The raw request body as bytes.

This property is loaded asynchronously from the request stream upon
first access and then cached.
```

## `Request.text`

```python
The request body decoded as a string (using UTF-8).
```

## `Request.json`

```python
The request body parsed as JSON.
```

## `Request.form`

```python
The request body parsed as form data.
```

## `headers`

```python
The request headers as a case-insensitive dictionary.
```

## `query`

```python
The parsed query parameters from the URL as a dictionary.
```

## `body`

```python
The raw request body as bytes.

This property is loaded asynchronously from the request stream upon
first access and then cached.
```

## `text`

```python
The request body decoded as a string (using UTF-8).
```

## `json`

```python
The request body parsed as JSON.
```

## `form`

```python
The request body parsed as form data.
```

