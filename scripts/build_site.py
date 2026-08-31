"""content/posts/*.md から静的サイトをビルドして public/ に出力するスクリプト。

使い方:
    python scripts/build_site.py
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import frontmatter
import markdown as md
import yaml
from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
PAGES_DIR = ROOT / "content" / "pages"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "public"
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_posts() -> list[dict]:
    posts = []
    if not CONTENT_DIR.exists():
        return posts

    for path in sorted(CONTENT_DIR.glob("*.md")):
        post = frontmatter.load(path)
        html_body = md.markdown(
            post.content,
            extensions=["extra", "tables", "sane_lists", "toc"],
        )
        posts.append(
            {
                "title": post.get("title", path.stem),
                "description": post.get("description", ""),
                "date": str(post.get("date", "")),
                "slug": post.get("slug", path.stem),
                "tags": post.get("tags", []),
                "html_body": html_body,
            }
        )

    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def load_pages(site: dict) -> list[dict]:
    pages = []
    if not PAGES_DIR.exists():
        return pages

    replacements = {
        "{{BASE_URL}}": site["base_url"],
        "{{CONTACT_EMAIL}}": site.get("contact_email", ""),
    }

    for path in sorted(PAGES_DIR.glob("*.md")):
        page = frontmatter.load(path)
        content = page.content
        for token, value in replacements.items():
            content = content.replace(token, value)
        html_body = md.markdown(content, extensions=["extra", "tables", "sane_lists"])
        pages.append(
            {
                "title": page.get("title", path.stem),
                "description": page.get("description", ""),
                "slug": page.get("slug", path.stem),
                "html_body": html_body,
            }
        )
    return pages


def build() -> None:
    config = load_config()
    site = config["site"]

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, OUTPUT_DIR / "static")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["asset"] = lambda p: site["base_url"] + p

    posts = load_posts()
    year = dt.date.today().year

    index_html = env.get_template("index.html").render(
        site=site, posts=posts, canonical_url=site["base_url"], year=year
    )
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    post_tpl = env.get_template("post.html")
    for post in posts:
        post_dir = OUTPUT_DIR / "posts" / post["slug"]
        post_dir.mkdir(parents=True, exist_ok=True)
        canonical = f"{site['base_url']}posts/{post['slug']}/"
        html = post_tpl.render(site=site, post=post, canonical_url=canonical, year=year)
        (post_dir / "index.html").write_text(html, encoding="utf-8")

    pages = load_pages(site)
    page_tpl = env.get_template("page.html")
    for page in pages:
        page_dir = OUTPUT_DIR / page["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        canonical = f"{site['base_url']}{page['slug']}/"
        html = page_tpl.render(site=site, page=page, canonical_url=canonical, year=year)
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    write_sitemap(site, posts, pages)
    write_robots(site)
    write_feed(site, posts)
    write_ads_txt(site)

    print(f"ビルド完了: {len(posts)}件の記事 + {len(pages)}件の固定ページ -> {OUTPUT_DIR}")


def write_sitemap(site: dict, posts: list[dict], pages: list[dict] | None = None) -> None:
    urls = [site["base_url"]]
    urls += [f"{site['base_url']}posts/{p['slug']}/" for p in posts]
    urls += [f"{site['base_url']}{p['slug']}/" for p in (pages or [])]
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'
    (OUTPUT_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")


def write_robots(site: dict) -> None:
    text = f"User-agent: *\nAllow: /\nSitemap: {site['base_url']}sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(text, encoding="utf-8")


def write_ads_txt(site: dict) -> None:
    client_id = site.get("monetization", {}).get("adsense_client_id", "")
    if not client_id:
        return
    pub_id = client_id.replace("ca-", "")
    text = f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n"
    (OUTPUT_DIR / "ads.txt").write_text(text, encoding="utf-8")


def write_feed(site: dict, posts: list[dict]) -> None:
    fg = FeedGenerator()
    fg.title(site["title"])
    fg.link(href=site["base_url"], rel="alternate")
    fg.description(site["description"])
    fg.language(site.get("language", "ja"))

    for post in posts[:20]:
        fe = fg.add_entry()
        fe.title(post["title"])
        fe.link(href=f"{site['base_url']}posts/{post['slug']}/")
        fe.description(post["description"])
        try:
            fe.pubDate(dt.datetime.fromisoformat(post["date"]).replace(tzinfo=dt.timezone.utc))
        except ValueError:
            pass

    fg.rss_file(str(OUTPUT_DIR / "feed.xml"))


if __name__ == "__main__":
    build()
