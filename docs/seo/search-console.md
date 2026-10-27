# Google Search Console: verifying the docs site and submitting the sitemap

None of this has been done yet. Do it after the docs site is deployed to GitHub Pages.

## 1. Add a URL-prefix property

The site is a GitHub *project* page under `abby306.github.io`, so you can't verify the whole
domain (that needs DNS control). Use a **URL-prefix** property:

1. Open https://search.google.com/search-console and choose **Add property → URL prefix**.
2. Enter `https://abby306.github.io/filemindr/` (with the trailing slash).

## 2. Verify ownership (HTML tag method)

1. Under **Other verification methods → HTML tag**, copy only the `content` value
   from `<meta name="google-site-verification" content="XXXX" />`.
2. Put it in `site/config.yaml`:
   ```yaml
   google_site_verification: "XXXX"
   ```
3. Commit, then run **Actions → Docs → Run workflow** with **deploy** checked.
4. Back in Search Console, click **Verify**. The tag is on every page, including the home page it checks.

The verification token isn't secret, but it is tied to your Google account. Committing it is normal.

## 3. Submit the sitemap

In the property: **Sitemaps → Add a new sitemap →** `https://abby306.github.io/filemindr/sitemap.xml`.

Why this step matters for this site: `robots.txt` is only read at a host's root
(`abby306.github.io/robots.txt`), so the `Sitemap:` line in the generated
`/filemindr/robots.txt` won't be discovered automatically. Submitting the sitemap directly
fixes that. On a custom domain later, robots.txt works as-is.

## 4. Request indexing for key pages

Use **URL inspection** on these and click **Request indexing**:

- `https://abby306.github.io/filemindr/`
- `https://abby306.github.io/filemindr/features/hybrid-search/`
- `https://abby306.github.io/filemindr/features/agentic-rag-citations/`
- `https://abby306.github.io/filemindr/features/ocr-document-processing/`

Indexing usually takes days to weeks and isn't guaranteed. Check **Pages** (coverage) and
**Performance** (queries, impressions) weekly for the first month.

## Bing (optional)

Bing Webmaster Tools can import a verified Search Console property in one click. Bing's index
also feeds some AI search products, so it's worth doing once Google is verified.
