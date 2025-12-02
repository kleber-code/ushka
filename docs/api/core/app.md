## `module`

```python
This module contains the core Ushka application class, responsible for handling HTTP requests,
managing routes, configuration, and running the ASGI server.
```

## `Ushka`

```python
The core Ushka application class.

This class handles application setup, request routing, middleware integration,
and server management. It acts as the central hub for the Ushka framework.
```

## `Ushka.handle_http_request`

```python
Handles an incoming HTTP request, routes it to the appropriate function,
and sends back the response.
```

## `Ushka.handle_lifespan`

```python
Handles ASGI lifespan events (startup and shutdown).
```

## `Ushka.handle_asgi_call`

```python
Dispatches incoming ASGI calls to the appropriate handler based on the scope type.
```

## `Ushka.run`

```python
Runs the Ushka application using Uvicorn.

Displays a startup banner, mapped routes, and then starts the ASGI server.
```

## `Ushka.get`

```python
Decorator to register a function as a GET route handler.
```

## `Ushka.post`

```python
Decorator to register a function as a POST route handler.
```

## `Ushka.put`

```python
Decorator to register a function as a PUT route handler.

Args:
    path: The URL path for the route.

Returns:
    The decorated function.
```

## `Ushka.update`

```python
Decorator to register a function as an UPDATE route handler.
```

## `Ushka.head`

```python
Decorator to register a function as a HEAD route handler.
```

## `Ushka.delete`

```python
Decorator to register a function as a DELETE route handler.
```

## `handle_http_request`

```python
Handles an incoming HTTP request, routes it to the appropriate function,
and sends back the response.
```

## `handle_lifespan`

```python
Handles ASGI lifespan events (startup and shutdown).
```

## `handle_asgi_call`

```python
Dispatches incoming ASGI calls to the appropriate handler based on the scope type.
```

## `run`

```python
Runs the Ushka application using Uvicorn.

Displays a startup banner, mapped routes, and then starts the ASGI server.
```

## `get`

```python
Decorator to register a function as a GET route handler.
```

## `post`

```python
Decorator to register a function as a POST route handler.
```

## `put`

```python
Decorator to register a function as a PUT route handler.

Args:
    path: The URL path for the route.

Returns:
    The decorated function.
```

## `update`

```python
Decorator to register a function as an UPDATE route handler.
```

## `head`

```python
Decorator to register a function as a HEAD route handler.
```

## `delete`

```python
Decorator to register a function as a DELETE route handler.
```

