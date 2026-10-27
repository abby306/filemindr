"""Validate the built docs site and the repo's Markdown links (offline).

    python site/build.py && python site/check.py

Checks, on `site/_build/`:
  * every page: one <title> (unique, <= 70 chars), meta description (50-160
    chars, unique), canonical == base_url + path, Open Graph + Twitter tags,
    exactly one <h1>, no skipped heading levels, <html lang>, viewport meta
  * JSON-LD blocks parse and carry @context/@type
  * internal links and anchors resolve; images exist and have alt text
  * sitemap.xml parses and lists exactly the canonical URLs; robots.txt
    points at it; llms.txt exists
And on Markdown sources (README, top-level docs, docs/, site/content/):
  * relative links resolve to files in the repo (and #anchors to headings)
  * links into github.com/abby306/filemindr/{blob,tree}/main/ name real paths
  * links to the docs site name real built pages
Exit code 1 on any failure. No network access needed.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import yaml

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
OUT = SITE_DIR / "_build"
CFG = yaml.safe_load((SITE_DIR / "config.yaml").read_text())
BASE = CFG["base_url"]
BASE_PATH = urlparse(BASE).path
REPO_URL = CFG["repo_url"].rstrip("/")

errors: list[str] = []


def err(where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._in_ld = False
        self.meta: dict[str, str] = {}
        self.links: list[tuple[str, str]] = []  # (rel, href)
        self.hrefs: list[str] = []
        self.imgs: list[tuple[str, str | None]] = []
        self.ids: set[str] = set()
        self.headings: list[int] = []
        self.json_ld: list[str] = []
        self.lang = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            self.links.append((a.get("rel", ""), a.get("href", "")))
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "img":
            self.imgs.append((a.get("src", ""), a.get("alt")))
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld = True
            self.json_ld.append("")
        elif re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_ld:
            self.json_ld[-1] += data


def url_to_file(url_path: str) -> Path | None:
    """Map a site URL path (/filemindr/x/) to a built file, or None if outside."""
    if not url_path.startswith(BASE_PATH):
        return None
    rel = unquote(url_path[len(BASE_PATH):])
    target = OUT / rel
    return target / "index.html" if (rel == "" or rel.endswith("/")) else target


def check_site() -> set[str]:
    if not OUT.is_dir():
        err("site", "site/_build missing — run python site/build.py first")
        return set()
    pages = sorted(p for p in OUT.rglob("index.html"))
    parsed: dict[Path, PageParser] = {}
    for f in pages + [OUT / "404.html"]:
        p = PageParser()
        p.feed(f.read_text(encoding="utf-8"))
        parsed[f] = p

    canonicals: set[str] = set()
    seen_titles: dict[str, Path] = {}
    seen_desc: dict[str, Path] = {}
    for f in pages:
        p = parsed[f]
        where = str(f.relative_to(OUT))
        rel_dir = f.parent.relative_to(OUT).as_posix()
        expected = BASE + ("" if rel_dir == "." else rel_dir + "/")
        title = p.title.strip()
        if not title:
            err(where, "missing <title>")
        elif len(title) > 70:
            err(where, f"title too long ({len(title)} > 70): {title!r}")
        if title in seen_titles:
            err(where, f"duplicate title with {seen_titles[title]}")
        seen_titles[title] = f
        desc = p.meta.get("description", "")
        if not 50 <= len(desc) <= 160:
            err(where, f"meta description length {len(desc)} not in 50..160")
        if desc in seen_desc:
            err(where, f"duplicate description with {seen_desc[desc]}")
        seen_desc[desc] = f
        canon = [h for rel, h in p.links if rel == "canonical"]
        if canon != [expected]:
            err(where, f"canonical {canon} != {expected}")
        canonicals.add(expected)
        for key in ("og:title", "og:description", "og:url", "og:image", "og:type",
                    "twitter:card", "viewport"):
            if not p.meta.get(key):
                err(where, f"missing meta {key}")
        if p.meta.get("og:url") != expected:
            err(where, "og:url != canonical")
        if p.lang != "en":
            err(where, "missing <html lang>")
        if p.headings.count(1) != 1:
            err(where, f"expected exactly one <h1>, found {p.headings.count(1)}")
        for prev, cur in zip(p.headings, p.headings[1:]):
            if cur > prev + 1:
                err(where, f"heading level skips h{prev} -> h{cur}")
        if not p.json_ld:
            err(where, "no JSON-LD structured data")
        for block in p.json_ld:
            try:
                data = json.loads(block)
                if "@context" not in data or "@type" not in data:
                    err(where, "JSON-LD block lacks @context/@type")
            except json.JSONDecodeError as exc:
                err(where, f"invalid JSON-LD: {exc}")

    # Links, anchors and images on every built HTML file (incl. 404).
    for f, p in parsed.items():
        where = str(f.relative_to(OUT))
        page_url = BASE + f.parent.relative_to(OUT).as_posix().strip(".") + "/"
        page_url = page_url.replace("//", "/").replace(":/", "://")
        for href in p.hrefs + [h for rel, h in p.links if rel in ("stylesheet", "icon", "sitemap")]:
            absolute = urljoin(page_url, href)
            u = urlparse(absolute)
            if u.netloc != urlparse(BASE).netloc:
                continue  # external: not checked offline
            target = url_to_file(u.path)
            if target is None or not target.exists():
                err(where, f"broken internal link {href}")
                continue
            if u.fragment and target.suffix == ".html":
                tp = parsed.get(target) or PageParser()
                if target not in parsed:
                    tp.feed(target.read_text(encoding="utf-8"))
                if u.fragment not in tp.ids:
                    err(where, f"missing anchor #{u.fragment} in {href}")
        for src, alt in p.imgs:
            if not alt:
                err(where, f"image without alt text: {src}")
            target = url_to_file(urlparse(urljoin(page_url, src)).path)
            if target is None or not target.exists():
                err(where, f"missing image {src}")

    # sitemap / robots / llms.txt
    try:
        tree = ET.parse(OUT / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = {e.text for e in tree.getroot().findall("s:url/s:loc", ns)}
        if locs != canonicals:
            err("sitemap.xml", f"URL set differs from canonicals: {sorted(locs ^ canonicals)}")
    except (ET.ParseError, FileNotFoundError) as exc:
        err("sitemap.xml", f"invalid: {exc}")
    robots = (OUT / "robots.txt").read_text() if (OUT / "robots.txt").exists() else ""
    if f"Sitemap: {BASE}sitemap.xml" not in robots:
        err("robots.txt", "missing Sitemap line")
    if re.search(r"(?m)^Disallow:\s*/\s*$", robots):
        err("robots.txt", "disallows everything")
    if not (OUT / "llms.txt").exists():
        err("llms.txt", "missing")
    return canonicals


# --- Markdown link checks ----------------------------------------------------

_MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)"
                      r"|<img[^>]+src=\"([^\"]+)\"|<a[^>]+href=\"([^\"]+)\"")


def github_slug(heading: str) -> str:
    s = re.sub(r"`|\*|_(?=\w)|(?<=\w)_", "", heading.strip().lower())
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def md_anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return {github_slug(m) for m in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*$", text)}


def check_markdown(built_urls: set[str]) -> None:
    files = [REPO_ROOT / n for n in ("README.md", "CONTRIBUTING.md", "SECURITY.md",
                                     "RUN.md", "CHANGELOG.md") if (REPO_ROOT / n).exists()]
    files += sorted((REPO_ROOT / "docs").rglob("*.md")) + sorted((SITE_DIR / "content").rglob("*.md"))
    files += sorted((REPO_ROOT / ".github").rglob("*.md"))
    for f in files:
        where = str(f.relative_to(REPO_ROOT))
        text = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.DOTALL)
        for m in _MD_LINK.finditer(text):
            link = next(g for g in m.groups() if g)
            if link.startswith("mailto:"):
                continue
            u = urlparse(link)
            if u.scheme in ("http", "https"):
                if link.startswith(BASE):
                    if f"{BASE}{u.path[len(BASE_PATH):]}" not in built_urls and not (
                            url_to_file(u.path) and url_to_file(u.path).exists()):
                        err(where, f"docs-site link to unknown page {link}")
                gh = re.match(re.escape(REPO_URL) + r"/(?:blob|tree)/main/([^#?]+)", link)
                if gh and not (REPO_ROOT / unquote(gh.group(1))).exists():
                    err(where, f"GitHub link to missing path {gh.group(1)}")
                continue
            if u.scheme:
                continue
            target = f if not u.path else (f.parent / unquote(u.path)).resolve()
            if not target.exists():
                err(where, f"broken relative link {link}")
                continue
            if u.fragment and target.suffix == ".md" and u.fragment not in md_anchors(target):
                err(where, f"missing anchor #{u.fragment} in {link}")


if __name__ == "__main__":
    urls = check_site()
    check_markdown(urls)
    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"ok: {len(urls)} pages, metadata, links, sitemap, robots.txt, llms.txt, Markdown links")
