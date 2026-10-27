# Documentation website

Source for the public Filemindr docs (https://abby306.github.io/filemindr/). A ~250-line
static generator. It uses no JavaScript framework and adds nothing to the app's dependencies.

```
site/
├── config.yaml        # base_url (the ONE place the public URL lives), nav order, site identity
├── content/           # pages: Markdown + YAML front matter (title, description, nav_title)
├── templates/         # page.html (meta, Open Graph, JSON-LD, nav), 404.html
├── static/            # style.css, favicon.svg
├── llms-intro.md      # summary paragraph for the generated llms.txt
├── build.py           # -> site/_build/ (HTML, sitemap.xml, robots.txt, llms.txt, assets)
└── check.py           # offline validation; exits 1 on problems
```

Images come from `docs/assets/` (shared with the README).

## Build and preview

```bash
python -m venv .venv-docs && .venv-docs/bin/pip install -r site/requirements.txt
.venv-docs/bin/python site/build.py --base-url http://localhost:8001/
.venv-docs/bin/python -m http.server 8001 -d site/_build    # open http://localhost:8001/
```

Before committing, build with the real URL and validate:

```bash
.venv-docs/bin/python site/build.py && .venv-docs/bin/python site/check.py
```

## Writing a page

1. Add `content/<slug>.md` (or `content/features/<slug>.md`) with front matter:
   ```yaml
   ---
   title: "Specific, searchable title (≤ 58 chars + ' | Filemindr')"
   nav_title: Short nav label
   description: "One or two sentences, 50–160 chars, saying what the page answers."
   ---
   ```
2. Start the body with exactly one `# H1`. Use `##` / `###` without skipping levels.
3. Link to other pages with relative `.md` links (`../architecture.md#tenancy-and-isolation`).
   They work on GitHub and are rewritten to site URLs at build time. Link to code with full
   `https://github.com/abby306/filemindr/blob/main/...` URLs (`check.py` verifies the paths exist).
4. Add the page's URL to `nav` in `config.yaml`. The build fails if a page isn't in the nav.

Keep content factual and tied to the code. If behaviour changes, update the page in the same PR.

## Deploying

The `Docs` workflow (`.github/workflows/docs.yml`) builds and validates on every PR that touches docs.
To publish:

1. Repository **Settings → Pages → Build and deployment → Source: GitHub Actions** (one-time).
2. **Actions → Docs → Run workflow** with **deploy** checked.

To move to a custom domain later, change `base_url` in `config.yaml`, add a `CNAME` file (copy it
into `_build` in `build.py`), and configure the domain in the Pages settings.
