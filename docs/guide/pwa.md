# Progressive Web App

Turn the app into something people can install and open offline-friendly, from
`ushka.toml`. It is off by default. When on, Ushka serves the manifest, a service
worker, the script that registers it and an offline page.

## Turn it on

```toml
[pwa]
enable = true
name = "My App"
short_name = "MyApp"
theme_color = "#2b1e3a"
background_color = "#ffffff"
icons = ["/static/icon-192.png", "/static/icon-512.png"]
```

Add the tags to your layout's `<head>`:

```html
<head>
  {{ seo() }}
  {{ pwa() }}
</head>
```

`{{ pwa() }}` writes the manifest link, the theme colour, an Apple touch icon and
the script that registers the worker. It shows nothing while `enable` is `false`.

Browsers want PNG icons of **192x192** and **512x512** to offer the install
button. The sizes are read from the file names (`icon-192.png`, `logo-512x512.png`);
for other names, use tables:

```toml
[[pwa.icons]]
src = "/static/logo.png"
sizes = "512x512"
purpose = "any maskable"
```

`ushka check` fails when `[pwa]` is on without both sizes.

## What is served

| Path | What |
| --- | --- |
| `/manifest.webmanifest` | The web app manifest, built from `[pwa]`. Name and description fall back to `[seo]` and `[app]`. |
| `/sw.js` | The service worker. |
| `/pwa.js` | Registers the worker. It is a file, not inline code, so the default [Content-Security-Policy](security.md) stays strict. |
| `/offline` | The page shown when a navigation fails for lack of network. |

You can replace any of them by defining the route yourself, for example your own
styled `/offline` page.

## What the service worker does

It is deliberately conservative. A worker that caches pages can show one person's
private page to the next person on a shared device, so:

- page navigations always go to the network; the offline page appears only when the network fails, and **pages are never cached**;
- only `GET` requests to your own origin are handled;
- the files under `[static]`, and any `cache_paths`, are served from the cache and refreshed in the background;
- `precache` lists extra URLs fetched when the worker installs.

Everything else is left to the browser. When you ship a new version of your static
files, change `cache_version` to drop every cache on the next visit.

## All the settings

| Key | Default | Meaning |
| --- | --- | --- |
| `enable` | `false` | Turn the PWA on. |
| `name`, `short_name` | `""` | App name; empty falls back to `[seo] site_name`, then `[app] name`. |
| `description` | `""` | Empty uses `[seo] description`. |
| `start_url`, `scope` | `"/"` | Where the app opens and what it controls. |
| `display` | `"standalone"` | `standalone`, `fullscreen`, `minimal-ui` or `browser`. |
| `orientation`, `lang`, `id`, `categories` | | Optional manifest fields. |
| `theme_color`, `background_color` | `"#1b1720"`, `"#ffffff"` | Colours of the title bar and the splash screen. |
| `icons` | `[]` | Paths, or `[[pwa.icons]]` tables with `src`, `sizes`, `type`, `purpose`. |
| `shortcuts` | `[]` | `[[pwa.shortcuts]]` tables with `name` and `url`, shown on long-press. |
| `offline` | `true` | Serve an offline page for failed navigations. |
| `offline_title`, `offline_message` | | Text of the built-in offline page. |
| `precache` | `[]` | Extra URLs fetched when the worker installs. They must all exist. |
| `cache_paths` | `[]` | Extra URL prefixes cached at runtime. |
| `cache_version` | `"1"` | Change it to drop every cache. |
| `manifest_path`, `sw_path`, `script_path`, `offline_path` | the paths above | Move the files. |

A worker can only control pages under its own path, and Ushka serves it from `/`
so it covers the whole site. HTTPS is required in production (`localhost` is
fine for development), as for every service worker.
