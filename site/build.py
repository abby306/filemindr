"""Build the Filemindr documentation site into static HTML.

    pip install -r site/requirements.txt
    python site/build.py                      # -> site/_build/
    python site/build.py --base-url http://localhost:8001/   # local preview
    python -m http.server 8001 -d site/_build

Pages are Markdown files under `site/content/` with a YAML front-matter block
(`title`, `description`, `nav_title`, optional `type: home|article`). URLs are
derived from file paths: `features/hybrid-search.md` -> `features/hybrid-search/`.
Relative `.md` links between pages are rewritten to those URLs, so the sources
also read correctly on GitHub. Everything public-facing (canonical URLs, Open
Graph, sitemap, robots.txt, llms.txt) derives from `base_url` in config.yaml.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import posixpath
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
CONTENT_DIR = SITE_DIR / "content"
OUT_DIR = SITE_DIR / "_build"
ASSETS_SRC = REPO_ROOT / "docs" / "assets"

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_MD_LINK = re.compile(r'href="(?!https?://|mailto:|#|/)([^"#]+?\.md)(#[^"]*)?"')


@dataclass
class Page:
    source: Path
    rel_url: str  # "" for home, "features/hybrid-search/" otherwise
    meta: dict
    body_md: str
    html: str = ""
    toc: list | None = None
    lastmod: str = ""

    @property
    def title(self) -> str:
        return self.meta["title"]

    @property
    def nav_title(self) -> str:
        return self.meta.get("nav_title", self.title)


def _rel_url_for(path: Path) -> str:
    rel = path.relative_to(CONTENT_DIR).with_suffix("")
    if rel.name == "index":
        rel = rel.parent
    s = rel.as_posix()
    return "" if s in ("", ".") else s + "/"


def _git_lastmod(path: Path) -> str:
    """Last commit date of a source file (falls back to today when uncommitted)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        out = ""
    return out or dt.date.today().isoformat()


def load_pages() -> list[Page]:
    pages = []
    for path in sorted(CONTENT_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = _FRONT_MATTER.match(text)
        if not m:
            raise SystemExit(f"{path}: missing front matter")
        meta = yaml.safe_load(m.group(1)) or {}
        for key in ("title", "description"):
            if not meta.get(key):
                raise SystemExit(f"{path}: front matter needs `{key}`")
        pages.append(Page(path, _rel_url_for(path), meta, text[m.end():],
                          lastmod=_git_lastmod(path)))
    return pages


def _rewrite_md_links(html: str, page: Page, base_path: str, known: set[str]) -> str:
    """`../architecture.md#x` -> `/filemindr/architecture/#x` (only for real pages)."""
    src_dir = page.source.parent.relative_to(CONTENT_DIR).as_posix()

    def repl(m: re.Match) -> str:
        target = posixpath.normpath(posixpath.join(src_dir, m.group(1)))
        rel = _rel_url_for(CONTENT_DIR / target)
        if rel not in known:
            raise SystemExit(f"{page.source}: link to unknown page {m.group(1)}")
        return f'href="{base_path}{rel}{m.group(2) or ""}"'

    return _MD_LINK.sub(repl, html)


def render_markdown(pages: list[Page], base_path: str) -> None:
    known = {p.rel_url for p in pages}
    for page in pages:
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"],
            extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}},
        )
        html = md.convert(page.body_md)
        # Asset links written as ../../docs/assets/... (GitHub-relative) -> site assets.
        html = re.sub(r'(src|href)="(?:\.\./)+docs/assets/', rf'\1="{base_path}assets/', html)
        page.html = _rewrite_md_links(html, page, base_path, known)
        page.toc = md.toc_tokens


def json_ld(page: Page, cfg: dict, url: str) -> list[dict]:
    publisher = {"@type": "Person", "name": "abby306", "url": "https://github.com/abby306"}
    if page.meta.get("type") == "home":
        return [
            {
                "@context": "https://schema.org",
                "@type": "SoftwareSourceCode",
                "name": cfg["site_name"],
                "alternateName": f'{cfg["site_name"]} — {cfg["tagline"]}',
                "description": cfg["description"],
                "url": url,
                "codeRepository": cfg["repo_url"],
                "license": cfg["license_url"],
                "programmingLanguage": ["Python", "TypeScript", "SQL"],
                "runtimePlatform": ["Python 3.12", "Node.js 20+", "PostgreSQL 16 + pgvector"],
                "version": cfg["version"],
                "author": publisher,
                "keywords": "open source RAG, retrieval-augmented generation, self-hosted RAG, "
                            "document AI, hybrid search, pgvector, agentic RAG, OCR, "
                            "document management, citations",
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": f'{cfg["site_name"]} documentation',
                "url": cfg["base_url"],
            },
        ]
    crumbs = [{"@type": "ListItem", "position": 1, "name": cfg["site_name"], "item": cfg["base_url"]},
              {"@type": "ListItem", "position": 2, "name": page.nav_title, "item": url}]
    return [
        {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": page.title,
            "description": page.meta["description"],
            "url": url,
            "dateModified": page.lastmod,
            "author": publisher,
            "isPartOf": {"@type": "WebSite", "name": f'{cfg["site_name"]} documentation',
                         "url": cfg["base_url"]},
            "about": {"@type": "SoftwareSourceCode", "name": cfg["site_name"],
                      "codeRepository": cfg["repo_url"]},
        },
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs},
    ]


def build(base_url: str) -> None:
    cfg = yaml.safe_load((SITE_DIR / "config.yaml").read_text())
    if base_url:
        cfg["base_url"] = base_url
    if not cfg["base_url"].endswith("/"):
        raise SystemExit("base_url must end with '/'")
    base_path = urlparse(cfg["base_url"]).path or "/"

    pages = load_pages()
    render_markdown(pages, base_path)
    by_url = {p.rel_url: p for p in pages}
    nav = [
        {"title": sec["title"], "items": [by_url[u] for u in sec["items"]]}
        for sec in cfg["nav"]
    ]
    missing = set(by_url) - {u for sec in cfg["nav"] for u in sec["items"]}
    if missing:
        raise SystemExit(f"pages missing from nav in config.yaml: {sorted(missing)}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copytree(SITE_DIR / "static", OUT_DIR / "static")
    shutil.copytree(ASSETS_SRC, OUT_DIR / "assets")
    (OUT_DIR / ".nojekyll").write_text("")

    env = Environment(loader=FileSystemLoader(SITE_DIR / "templates"),
                      autoescape=select_autoescape(["html"]))
    tpl = env.get_template("page.html")
    flat = [p for sec in nav for p in sec["items"]]
    for i, page in enumerate(flat):
        url = cfg["base_url"] + page.rel_url
        html = tpl.render(
            cfg=cfg, page=page, url=url, base_path=base_path, nav=nav,
            prev=flat[i - 1] if i > 0 else None,
            next=flat[i + 1] if i + 1 < len(flat) else None,
            json_ld=[json.dumps(x, ensure_ascii=False) for x in json_ld(page, cfg, url)],
            social_image=cfg["base_url"] + cfg["social_image"],
            source_url=f'{cfg["repo_url"]}/blob/main/site/content/'
                       f'{page.source.relative_to(CONTENT_DIR).as_posix()}',
        )
        dest = OUT_DIR / page.rel_url / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")

    (OUT_DIR / "404.html").write_text(env.get_template("404.html").render(
        cfg=cfg, base_path=base_path, nav=nav), encoding="utf-8")

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page in flat:
        sitemap.append(f'  <url><loc>{cfg["base_url"]}{page.rel_url}</loc>'
                       f'<lastmod>{page.lastmod}</lastmod></url>')
    sitemap.append("</urlset>")
    (OUT_DIR / "sitemap.xml").write_text("\n".join(sitemap) + "\n")

    # robots.txt is only honored at a host's root. On a project Pages site
    # (user.github.io/repo/) crawlers read the user site's robots.txt instead, so
    # submit the sitemap in Search Console too. It is correct as-is on a custom domain.
    (OUT_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {cfg['base_url']}sitemap.xml\n")

    lines = [f"# {cfg['site_name']}", "", f"> {cfg['description'].strip()}", "",
             (SITE_DIR / "llms-intro.md").read_text().strip(), "", "## Documentation", ""]
    for page in flat:
        lines.append(f"- [{page.title}]({cfg['base_url']}{page.rel_url}): "
                     f"{page.meta['description']}")
    lines += ["", "## Source", "",
              f"- [GitHub repository]({cfg['repo_url']}): source code, issues, AGPL-3.0 license",
              f"- [README]({cfg['repo_url']}#readme): overview and quickstart", ""]
    (OUT_DIR / "llms.txt").write_text("\n".join(lines))

    print(f"built {len(flat)} pages -> {OUT_DIR.relative_to(REPO_ROOT)} (base {cfg['base_url']})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="", help="override config.yaml base_url (preview)")
    build(ap.parse_args().base_url)
