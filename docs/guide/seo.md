# SEO

SEO is ready from the first request. Ushka writes the title, description,
canonical link, Open Graph and Twitter tags and structured data for you, and
serves `robots.txt` and `sitemap.xml`. You edit a few values in `ushka.toml` and,
when a page needs something different, say so on that page.

## Set it up

Put `{{ seo() }}` in the `<head>` of your layout, **instead of `<title>`**:

```html
<head>
  <meta charset="utf-8">
  {{ seo() }}
</head>
```

`ushka new` already does this. Then fill in `[seo]`:

```toml
[seo]
url = "https://example.com"        # your public address
description = "Build secure web apps without the boilerplate."
image = "/static/social.png"       # preview image for shared links
twitter_site = "@example"
```

That is enough. Every page now has a title, a description, a canonical URL, a
robots rule, Open Graph and Twitter tags, and the home page also carries
`WebSite` structured data.

!!! tip
    Set `url`. Without it Ushka does not know your public address, so it leaves
    the canonical link out and answers `404` for `sitemap.xml`. In debug mode, or
    when `[security] allowed_hosts` is set, it uses the address of the request
    instead. It never trusts a `Host` header nobody checked, because that would
    let anyone put their own domain into your canonical links.

## Change one page

Pass what differs, in the template:

```html
{{ seo(title="About us", description="Who we are and why.") }}
```

or from the handler, with a `page_seo` dict:

```python
async def get(request, slug: str):
    post = await Post.get(slug=slug)
    return await render(request, "post.html", {
        "post": post,
        "page_seo": {
            "title": post.title,
            "description": post.summary,
            "image": post.cover,
            "type": "article",
            "published": post.created.isoformat(),
            "author": post.author,
        },
    })
```

A title goes through `title_template`, so "About us" becomes
`About us · My Site`. Values are escaped, so client data in a title cannot break
out of a tag, and URLs other than paths and `http(s)` are dropped.

| Option | What it does |
| --- | --- |
| `title` | Page title; the site name is added by `title_template`. |
| `description` | Meta and social description. |
| `image`, `image_alt` | Social preview image, a path or a URL. |
| `type` | `website` (default) or `article`, which adds `Article` structured data. |
| `published`, `modified`, `author` | For articles. |
| `noindex=True` | `noindex, nofollow` for this page (login, thank-you pages). |
| `robots` | Any other robots rule, such as `"noindex, follow"`. |
| `canonical` | A different canonical URL, a path or a URL. |
| `alternates` | `{"pt-BR": "/pt/"}` writes the `hreflang` links. |
| `jsonld` | Your own structured data, a dict or a list of dicts. |
| `path`, `locale` | Override the path used for the canonical URL, or the Open Graph locale. |

An unknown option is an error rather than silence, so a typo does not quietly
lose your tags.

## All the settings

| Key | Default | Meaning |
| --- | --- | --- |
| `enable` | `true` | `seo()`, `robots.txt` and `sitemap.xml`. `false` turns it all off. |
| `url` | `""` | Public origin, such as `https://example.com`. |
| `site_name` | `""` | Empty uses `[app] name`. |
| `title` | `""` | Title of pages that set none (usually the home page). |
| `title_template` | `"{title} · {site_name}"` | How a page title is combined with the site name. |
| `description` | `""` | Default description. |
| `image`, `image_alt` | `""` | Default social image. |
| `locale` | `"en_US"` | Open Graph locale. |
| `type` | `"website"` | Default Open Graph type. |
| `robots` | `"index, follow"` | Use `"noindex, nofollow"` to keep a staging site out of search. |
| `author` | `""` | Default author. |
| `twitter_site`, `twitter_card` | `""`, `"summary_large_image"` | Twitter/X tags. |
| `jsonld` | `true` | Structured data (`WebSite` on `/`, `Article` for articles). |
| `robots_txt` | `true` | Serve `/robots.txt`. |
| `robots_disallow` | `[]` | Paths for `Disallow:` lines. |
| `sitemap` | `true` | Serve `/sitemap.xml`. |
| `sitemap_paths` | `[]` | Extra paths to list. |
| `sitemap_exclude` | `["/api/*", "/admin/*", "/_*"]` | Patterns left out of the sitemap. |

Like every setting, they can come from the environment: `USHKA_SEO_URL=...`.

## robots.txt and sitemap.xml

`/robots.txt` allows everything (or disallows everything when `robots` contains
`noindex`) and points to the sitemap.

`/sitemap.xml` lists your plain `GET` pages, the ones without parameters. It
skips the [static files](static_files.md), the API, `robots.txt` itself, anything
with a file extension other than `.html`, and whatever matches
`sitemap_exclude`. **Check the list once**: a private page that is a plain `GET`
route would be listed, so add it to `sitemap_exclude` (patterns end with `*`,
for example `"/account/*"`).

Pages with parameters, such as blog posts, come from code:

```python
@app.sitemap_source
async def posts():
    rows = await Post.all()
    return [(f"/blog/{p.slug}", p.updated.date().isoformat()) for p in rows]
```

Return paths, or `(path, lastmod)` pairs. The function may be sync or async. A few
fixed extras can also go in `sitemap_paths`.

## Your own routes win

If you define `/robots.txt` or `/sitemap.xml` yourself, yours is used, with no
warning. The same goes for the [PWA](pwa.md) files.

## Check before going live

`ushka check` warns when `url` is missing or `description` is empty, and
`ushka check --production` also warns if `robots` says `noindex`.
