## `module`

```python
This module defines custom exception classes for the Ushka framework.

These exceptions are used throughout the framework to indicate various
error conditions, from routing and response handling to server-side issues.
```

## `ServerError`

```python
Base exception for all server-related errors in Ushka.
```

## `RouterError`

```python
Base exception for errors related to the routing system.
```

## `InvalidArgument`

```python
Raised when an invalid argument is provided to a router function.
```

## `ResponseError`

```python
Base exception for errors that occur during response handling.
```

## `ContentToTextParserFailed`

```python
Raised when content cannot be parsed or converted to a text string.
```

## `ContentToJsonParserFailed`

```python
Raised when content fails to be serialized into a JSON string.
```

## `StatictServerError`

```python
Base exception for errors related to the static file server.
```

## `CantCompleteResponse`

```python
Raised when the server is unable to complete or send a response.
```

