## `module`

```python
This module provides utilities for handling errors and tracebacks.

It includes functions for extracting detailed, yet safe, traceback information,
including code context and local variables. A key feature is the automatic
redaction of sensitive data (e.g., passwords, tokens) from local variables
to prevent them from being exposed in logs or debug pages.
```

## `safe_repr`

```python
Creates a safe string representation of an object.

It truncates long representations and handles potential errors during the
`repr()` call.

Args:
    obj: The object to represent.
    limit: The maximum length of the string representation before
        truncation.

Returns:
    A safe, string representation of the object.
```

## `get_safe_locals`

```python
Retrieves local variables from a frame, redacting sensitive information.

It inspects the local variables of a given frame and redacts any values
whose keys match a list of sensitive keywords (e.g., 'password', 'token').

Args:
    frame: The frame object to inspect.

Returns:
    A dictionary of local variables with sensitive values redacted.
```

## `get_code_lines_context`

```python
Retrieves a block of code lines surrounding a specific line number.

Args:
    filename: The path to the source file.
    lineno: The central line number to get context around.
    context: The number of lines to show before and after the central line.

Returns:
    A list of tuples, where each tuple contains a line number and the
    corresponding line of code.
```

## `get_copy_paste_traceback`

```python
Formats an exception's traceback into a plain string.

This is useful for creating a simple, copy-pasteable version of the
traceback for logs or issue reports.

Args:
    exc: The exception object.

Returns:
    The formatted traceback as a single string.
```

## `extract_frames`

```python
Extracts detailed information from each frame of a traceback.

This function walks through an exception's traceback and, for each frame,
gathers the file path, line number, function name, code context, and a
sanitized dictionary of local variables.

Args:
    exc: The exception object.

Returns:
    A list of dictionaries, where each dictionary represents a single
    frame from the traceback.
```

