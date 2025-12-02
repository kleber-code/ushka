## `module`

```python
This module provides functionality for serving static files in the Ushka framework.

It includes functions to resolve static file paths and to serve files with
appropriate security checks and HTTP headers.
```

## `get_static_absolute_path`

```python
Resolves the absolute path for a static directory.

This function handles both relative and absolute paths for the static
directory. If the path is relative, it is resolved against the application's
working directory.

Args:
    workdir: The application's working directory.
    static_dir: The configured static directory path (can be relative or
        absolute).

Returns:
    The absolute path to the static directory.
```

## `server_static_files`

```python
Serves a static file based on the provided filename.

This function performs security checks to prevent path traversal attacks,
verifies that the file exists, and sets the appropriate HTTP headers
(e.g., `Content-Type`, `Content-Length`).

Args:
    filename: The name of the file to serve, relative to the static
        directory.
    config: The application configuration object.
    response: The response object to populate with the file content and
        headers.

Returns:
    The populated response object.

Raises:
    HttpStaticServerNotFound: If the file is not found, is not a file,
        or if a path traversal attack is detected.
    CantCompleteResponse: If there is an error reading the file or
        populating the response.
```

