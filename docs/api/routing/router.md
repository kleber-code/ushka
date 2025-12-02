## `module`

```python
This module implements the Router for the Ushka framework.

It handles route registration, discovery, and matching for both static and
dynamic URL paths. The Router is a key component for mapping incoming HTTP
requests to the appropriate handler functions.
```

## `normalize_url_path`

```python
Normalizes a URL path by removing empty segments.

Ensures that the path starts with a leading slash and removes any redundant
'/' or '.' characters.

Args:
    path: The raw URL path string.

Returns:
    The normalized URL path.
```

## `Router`

```python
Manages the application's routing logic.

This class is responsible for route registration, automatic discovery of
route handlers from files, and matching incoming requests to the correct
handler. It supports static paths, dynamic paths with parameters, and
dependency injection for handlers.

Attributes:
    workdir (Path): The application's working directory.
    logsystem (LogSystem): The logging system instance.
    static_routes (dict): A dictionary to store static routes.
    dynamic_routes (dict): A dictionary to store dynamic routes.
    host (str): The host address.
```

## `Router.add_route`

```python
Adds a new route to the router.

This method registers a handler for a given HTTP method and path. It
supports both static paths (e.g., '/users') and dynamic paths with
parameter capturing (e.g., '/users/[user_id]').

Args:
    method: The HTTP method (e.g., 'GET', 'POST').
    path: The URL path for the route.
    func: The handler function to execute for this route.
```

## `Router.get_route`

```python
Finds the appropriate route handler for a given request.

It prioritizes static routes for performance, falling back to dynamic
routes if no static match is found.

Args:
    request: The incoming request object.

Returns:
    A tuple containing the matched handler function and its resolved
    arguments, or `(None, None)` if no route is found.
```

## `Router.autodiscover`

```python
Automatically discovers and registers routes from a specified folder.

This method scans for Python files in the given folder, looking for
functions named after HTTP methods (e.g., `get`, `post`). It then
constructs a route path based on the file's location and registers it.

Args:
    folder: The name of the folder to scan for route modules.
```

## `Router.get_urls`

```python
Generates a formatted list of all registered URL paths.

Args:
    host: The server host, used for generating full URLs.
    port: The server port, used for generating full URLs.
    with_host: Whether to include the host and port in the output URLs.

Returns:
    A sorted list of strings, each representing a registered route
    and its supported HTTP methods.
```

