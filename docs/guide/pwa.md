# Progressive Web App

```python
app.use(Pwa(name="Shop", icons=["/static/icon-192.png", "/static/icon-512.png"], theme_color="#2b1e3a"))
```

Using it turns the PWA on: Ushka serves the manifest, a service worker, the script that registers it
and an offline page. Add the tags to your layout's `<head>`:

```html
<head>
  {{ seo() }}
  {{ pwa() }}
</head>
```

`Pwa(name=, icons=, theme_color=, **options)`: `options` are any other key of `[pwa]` below. The same
works from the file, and the file and the environment win over code (`enable = false` there turns it off):

```toml
[pwa]
enable = true
name = "Shop"
icons = ["/static/icon-192.png", "/static/icon-512.png"]
```

Browsers want PNG icons of **192x192** and **512x512** to offer the install button. Sizes are read from
the file names (`icon-192.png`, `logo-512x512.png`); for other names use tables:

```toml
[[pwa.icons]]
src = "/static/logo.png"
sizes = "512x512"
purpose = "any maskable"
```

`ushka check` fails when the PWA is on without both sizes.

## What is served

| Path | What |
| --- | --- |
| `/manifest.webmanifest` | The manifest. Name and description fall back to `[seo]` and `[app]`. |
| `/sw.js` | The service worker. |
| `/pwa.js` | Registers the worker. A file, not inline code, so the default [CSP](security.md) stays strict. |
| `/offline` | Shown when a navigation fails for lack of network. |

Define the route yourself to replace any of them, for example a styled `/offline` page.

## The service worker is conservative

A worker that caches pages can show one person's private page to the next person on a shared device, so
navigations always go to the network (the offline page appears only when it fails) and **pages are never
cached**. Only `GET` requests to your own origin are handled; `[static]` files and `cache_paths` are served
from the cache and refreshed in the background; `precache` lists URLs fetched at install. After shipping new
static files, change `cache_version` to drop every cache. HTTPS is required in production, as for any
service worker.

## Settings, `[pwa]`

| Key | Default | Meaning |
| --- | --- | --- |
| `enable` | `false` | On. `app.use(Pwa())` sets it. |
| `name`, `short_name`, `description` | `""` | Empty falls back to `[seo]`, then `[app] name`. |
| `start_url`, `scope` | `"/"` | Where the app opens and what it controls. |
| `display` | `"standalone"` | `standalone`, `fullscreen`, `minimal-ui` or `browser`. |
| `theme_color`, `background_color` | `"#1b1720"`, `"#ffffff"` | Title bar and splash screen. |
| `icons` | `[]` | Paths, or `[[pwa.icons]]` tables (`src`, `sizes`, `type`, `purpose`). |
| `shortcuts` | `[]` | `[[pwa.shortcuts]]` tables (`name`, `url`), shown on long-press. |
| `offline`, `offline_title`, `offline_message` | `true` | Show the offline page, and its title and text. |
| `precache`, `cache_paths`, `cache_version` | `[]`, `[]`, `"1"` | Install-time URLs, runtime prefixes, cache reset. |
| `orientation`, `lang`, `id`, `categories` | | Optional manifest fields. |
| `manifest_path`, `sw_path`, `script_path`, `offline_path` | the paths above | Move the files. |
