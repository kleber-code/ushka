# SEO

```python
app.use(Seo(url="https://shop.example", description="Handmade shoes"))
```

That is all. Every page gets a title, description, canonical link, robots rule, Open Graph and
Twitter tags and structured data, and `/robots.txt` and `/sitemap.xml` are served. SEO is already on
without that line: `Seo(...)` only gives the defaults, and `[seo]` in `ushka.toml` (or `USHKA_SEO_*`)
still wins, so staging and production differ by file or variable, not by edit.

`Seo(url=, description=, image=, **options)`: `options` are any other key of the `[seo]` table below.

Put `{{ seo() }}` in the `<head>` of your layout, **instead of `<title>`** (`ushka new` does):

```html
<head>
  <meta charset="utf-8">
  {{ seo() }}
</head>
```

!!! tip
    Set `url`. Without it there is no canonical link and `sitemap.xml` is a `404`. In debug mode, or
    with `[security] allowed_hosts`, the address of the request is used instead; a `Host` header nobody
    checked is never trusted.

## One page

```html
{{ seo(title="About us", description="Who we are and why.") }}
```

or from the handler:

```python
return await render(request, "post.html", {
    "post": post,
    "page_seo": {"title": post.title, "description": post.summary, "type": "article",
                 "published": post.created.isoformat(), "author": post.author},
})
```

| Option | What it does |
| --- | --- |
| `title` | Page title, put through `title_template` (`About us · My Site`). |
| `description`, `image`, `image_alt` | Meta and social card. `image` is a path or a URL. |
| `type` | `website` (default) or `article` (adds `Article` structured data). |
| `published`, `modified`, `author` | For articles. |
| `noindex=True` | `noindex, nofollow` for this page. `robots` takes any other rule. |
| `canonical` | A different canonical URL. |
| `alternates` | `{"pt-BR": "/pt/"}` writes the `hreflang` links. |
| `jsonld` | Your own structured data, a dict or a list. |
| `path`, `locale` | Override the path of the canonical URL, or the Open Graph locale. |

Values are escaped and unsafe URLs are dropped. An unknown option is an error, so a typo does not
quietly lose your tags.

## Settings, `[seo]`

| Key | Default | Meaning |
| --- | --- | --- |
| `enable` | `true` | `false` turns off `seo()`, `robots.txt` and `sitemap.xml`. |
| `url` | `""` | Public origin, such as `https://example.com`. |
| `site_name`, `title` | `""` | Site name (empty uses `[app] name`) and the title of pages with none. |
| `title_template` | `"{title} · {site_name}"` | How a title and the site name combine. |
| `description`, `image`, `image_alt` | `""` | Defaults for the card. |
| `locale`, `type` | `"en_US"`, `"website"` | Open Graph locale and type. |
| `robots` | `"index, follow"` | `"noindex, nofollow"` keeps a staging site out of search. |
| `author`, `twitter_site`, `twitter_card` | | Author and Twitter/X tags. |
| `jsonld` | `true` | `WebSite` on `/`, `Article` for articles. |
| `robots_txt`, `robots_disallow` | `true`, `[]` | Serve `/robots.txt`; its `Disallow:` paths. |
| `sitemap`, `sitemap_paths`, `sitemap_exclude` | `true`, `[]`, `["/api/*", "/admin/*", "/_*"]` | Serve `/sitemap.xml`; extra paths; patterns left out. |

## robots.txt and sitemap.xml

`/robots.txt` allows everything (or nothing when `robots` has `noindex`) and points to the sitemap.
`/sitemap.xml` lists your plain `GET` pages without parameters, skipping static files, the API and
anything that matches `sitemap_exclude`. **Check the list once**: a private page that is a plain `GET`
route would be listed, so add it to `sitemap_exclude` (patterns end with `*`, such as `"/account/*"`).

Pages with parameters come from code, sync or async, as paths or `(path, lastmod)` pairs:

```python
@app.sitemap_source
async def posts():
    return [(f"/blog/{p.slug}", p.updated.date().isoformat()) for p in await Post.all()]
```

A route of yours at `/robots.txt` or `/sitemap.xml` wins, with no warning (as for the [PWA](pwa.md) files).
`ushka check` warns when `url` or `description` is empty, and `--production` when `robots` says `noindex`.
