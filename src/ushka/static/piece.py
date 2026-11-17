"""`Static`: the piece that serves static files, ``app.use(Static("public", url="/assets"))``."""

from __future__ import annotations

from .files import DEFAULT_CACHE_CONTROL


class Static:
    """Serves static files: ``app.use(Static("public", url="/assets"))``.

    With a folder it is ``app.mount_static`` (any number of mounts). With no folder it turns
    on the ``[static]`` one, whose options are the keys of that section, so ``ushka.toml``
    and the environment can still change them per environment::

        app.use(Static())                      # ./static under /static
        app.use(Static(url="/files"))          # [static] url, as a default

    Parameters
    ----------
    directory : str or Path, optional
        Folder to serve, relative to the app directory.
    url : str, optional
        URL prefix.
    html : bool
        Mounts only: serve ``index.html`` for folders (a static-site build).
    cache_control : str, optional
        ``Cache-Control`` of every file.
    """

    def __init__(self, directory=None, url: str | None = None, *, html: bool = False, cache_control: str | None = None) -> None:
        if directory is None and html:
            raise TypeError("Static(html=True) needs a folder: Static('site', html=True)")
        self.directory, self.url, self.html, self.cache_control = directory, url, html, cache_control
        self.name = "static" if directory is None else f"static:{url or ''}"

    def install(self, app) -> None:
        if self.directory is not None:
            app.mount_static(
                self.url or app.config.get("static_url", "/static"),
                self.directory,
                html=self.html,
                cache_control=self.cache_control or app.config.get("static_cache_control") or DEFAULT_CACHE_CONTROL,
            )
            return
        values: dict = {"enable": True}
        if self.url is not None:
            values["url"] = self.url
        if self.cache_control is not None:
            values["cache_control"] = self.cache_control
        app.config.defaults("static", **values)
        app._serve_static_folder()
