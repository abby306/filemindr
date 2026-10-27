---
title: "Building an OCR-Powered PDF RAG System with Source-Grounded AI Answers"
description: "Text-layer probing, OCR fallback for scanned PDFs, page and bounding-box provenance, and citation validation in an open-source RAG pipeline."
tags: [rag, ocr, pdf, citations, document-ai, python, llm]
canonical_url: "TODO — set to the docs-site copy (e.g. https://abby306.github.io/filemindr/...) or the first place this is published"
status: draft — not published
---

# Building an OCR-Powered PDF RAG System with Source-Grounded AI Answers

A RAG answer you can't check is a liability. In a document archive the stakes
are concrete: a wrong renewal date on a lease or a wrong total on an invoice
costs money. So the goal for a PDF RAG system with citations isn't just "an
answer with a footnote". It's an answer where every claim links to the page —
ideally the region of the page — it came from, and where the system says
"that isn't in your documents" instead of guessing.

This article follows a document through the OCR RAG pipeline in
[Filemindr](https://github.com/abby306/filemindr), an open-source RAG and
document intelligence app, and shows where provenance gets captured, carried
and enforced. The relevant code is
[`app/services/ocr.py`](https://github.com/abby306/filemindr/blob/main/app/services/ocr.py),
[`app/services/extraction.py`](https://github.com/abby306/filemindr/blob/main/app/services/extraction.py)
and
[`app/services/synthesis.py`](https://github.com/abby306/filemindr/blob/main/app/services/synthesis.py).

## Provenance starts at OCR

Provenance is painful to retrofit. If your OCR step returns a flat string, no
amount of clever prompting later will tell you which page a fact came from. So
the first rule is that OCR output is structured: per page, per block, with
coordinates.

```python
@dataclass
class OcrBlock:
    text: str
    bbox: list[list[float]]  # polygon vertices [[x, y], ...]

@dataclass
class OcrPage:
    page: int
    text: str
    blocks: list[OcrBlock] = field(default_factory=list)
```

Every engine — native PDF text, Google Vision, DOCX — normalizes to this shape,
so everything downstream works the same way whatever the input was.

## Routing: text layer first, OCR only when needed

Running OCR on every PDF is slow, costs money, and is *less* accurate than
reading a PDF's embedded text when that text exists. So Filemindr probes first:

```python
_MIN_TOTAL_CHARS = 100
_MIN_CHARS_PER_PAGE = 20

def probe_pdf_text_layer(path):
    page_texts: list[str] = []
    with fitz.open(path) as doc:
        page_count = doc.page_count
        for page in doc:
            page_texts.append(page.get_text("text"))
    total_chars = sum(len(t.strip()) for t in page_texts)
    has_layer = (
        page_count > 0
        and total_chars >= _MIN_TOTAL_CHARS
        and (total_chars / page_count) >= _MIN_CHARS_PER_PAGE
    )
    return page_texts, page_count, has_layer
```

The two thresholds catch the common **scanned PDF** cases: a scan with no text
at all, and a scan whose only "text" is a page number or a stray watermark
string. The per-page average stops one text-heavy cover page from passing a
50-page scan.

The routing table is a pure function, which makes it easy to test:

| Input | Engine |
|---|---|
| PDF with usable text layer | PyMuPDF (`pdf_text_layer`) |
| PDF without (scanned) | rasterize each page → Google Vision |
| PNG / JPEG | Google Vision |
| DOCX | `python-docx` paragraphs |

### Native PDFs still get bounding boxes

For text-layer PDFs, PyMuPDF's `get_text("blocks")` returns rectangles. These
are converted to the same 4-vertex polygon shape Vision produces, so later code
doesn't care which engine ran:

```python
for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
    clean = text.strip()
    if not clean:
        continue
    bbox = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    blocks.append(OcrBlock(text=clean, bbox=bbox))
```

### The scanned PDF path

For scanned PDFs, each page is rasterized at 200 DPI and sent to Google Cloud
Vision's `document_text_detection`, which returns block-level polygons. Two
practical details:

- **Rasterize serially, OCR in parallel.** PyMuPDF isn't thread-safe on a shared
  document, so pages are rendered to PNG bytes first; the network calls then run
  through a bounded thread pool (`MAX_PARALLEL_CALLS`, default 4).
- **Tolerate bad pages.** Transient Vision errors (429, 500, 503, 504, deadline
  exceeded) are retried with backoff. A page that still fails is recorded in
  `failed_pages` with empty text rather than failing the document. Only an
  all-pages failure raises.

OCR results are cached on disk keyed by the file's SHA-256, so re-processing a
document (or re-uploading the same bytes) never pays for OCR twice.

DOCX is the weak spot: `python-docx` gives paragraph text but no pages or
coordinates, so a DOCX document is treated as one page and its facts carry no
bounding box. Citations still name the document, but can't highlight a region.

## Extraction: carry the page through the LLM

The next step turns OCR text into structured facts with one LLM call per page
window. The page numbers survive the round-trip because they're written into
the prompt:

```python
def _page_marker(page: int) -> str:
    return f"\n\n===== PAGE {page} =====\n"
```

and the system prompt instructs the model to set the `page` of every fact and
date to the marker it appears under. Pages are packed whole into chunks of up
to 14,000 characters, so a page is never split across calls, and long
documents are covered end to end rather than truncated.

The model returns atomic facts — self-contained sentences with pronouns
resolved — and typed facts (`label`, `value`, `value_numeric`, `unit`, `page`).
Atomic facts become the primary retrieval unit.

### Matching facts back to regions

The model paraphrases, so an atomic fact won't exactly match any OCR block. To
attach a bounding box, Filemindr uses token overlap against the blocks on the
fact's page and only trusts a match above 50%:

```python
fact_tokens = {t for t in text.lower().split() if len(t) > 2}
...
for block in ocr_page.blocks:
    block_tokens = {t for t in block.text.lower().split() if len(t) > 2}
    if not block_tokens:
        continue
    overlap = len(fact_tokens & block_tokens) / len(fact_tokens)
    if overlap > best_overlap:
        best_overlap = overlap
        best_bbox = block.bbox
if best_bbox is None or best_overlap < _BBOX_MIN_OVERLAP:   # 0.5
    return None
return {"page": page, "bbox": best_bbox}
```

It's deliberately best-effort. A fact with no confident match still has its
page; it just doesn't get a highlight. A wrong highlight is worse than none.

## Indexing

Atomic facts are embedded locally with `BAAI/bge-base-en-v1.5` and stored in
`document_facts` with their `page` and `bbox` alongside a pgvector embedding and
a generated full-text `tsvector`. Retrieval is hybrid — vector, full-text and
structured lookups fused with Reciprocal Rank Fusion, then a cross-encoder
rerank (covered in a separate article). What matters here is that **every hit
already carries a citation target**. Nothing needs to be re-located after
retrieval.

## Grounded answers: citations the model can't fake

Generation is where most "cited" RAG systems quietly lose their guarantees. If
you ask a model to output source names or page numbers, it can invent them.
Filemindr's answer loop closes that gap in three ways.

**1. The model only sees short ids.** Candidate facts are registered as `f1`,
`f2`, ...; documents as `d1`, `d2`. The model answers by calling a `finish` tool:

```text
finish(answer, cited_fact_ids, supported)
```

Function calling runs in `ANY` mode, so every model turn is a structured tool
call, never free text.

**2. Citations are validated against what was actually handed over:**

```python
for short in args.get("cited_fact_ids", []) or []:
    hit = facts.get(str(short))
    if hit is None or hit.key in seen:  # drop hallucinated / duplicate ids
        continue
    seen.add(hit.key)
    citations.append(Citation(
        fact_id=hit.fact_id, document_id=hit.document_id,
        title=titles.get(hit.document_id), page=hit.page,
    ))
```

An invented id simply disappears. Every surviving citation resolves to a real
`document_id`, `page` and (for atomic facts) a `fact_id` whose `bbox` the web
app highlights on the rendered page.

**3. "Not supported" is a first-class answer.** The system prompt tells the
model to answer only from the provided facts and summaries, and to finish with
`supported=false` when they don't contain the answer. The UI renders that as
an explicit "not in your documents". When that happens, a single GPT-4o pass
re-reasons over the same candidate pool. Its answer is adopted only if it also
claims support, and its citations go through the same validation. If no OpenAI
key is configured, this step is skipped and the honest negative stands.

### When extracted facts aren't enough

Extraction distills; it doesn't preserve everything. Tables, column lists and
exact clause wording often lose detail. So the agent has a `read_page` tool
that returns up to 4,000 characters of the page's raw OCR text from the cache.
The returned page itself becomes a citable candidate, so an answer read from a
page still cites that page.

There is also a guard for a subtle failure: in a follow-up about document A,
the model answering "unsupported" without having read any of A's pages. The
loop rejects that once, auto-reads the most relevant pages of the conversation's
documents, and lets the model try again. A similar one-time rejection catches
answers whose citations all come from a *different* document the answer never
names.

The loop is bounded to five model turns, with `finish` forced on the last.

## What the user sees

In the web app, each answer shows citation pills with document title and page.
Clicking one opens the document view on that page with the cited block
highlighted. The streaming endpoint sends the agent's steps over Server-Sent
Events ("searched your archive · 2 sources"), and every turn persists a
`retrieval_traces` row with candidates, citations, model and token counts, so
an answer can be audited after the fact.

## Limitations

- **Google Vision is required** for scanned PDFs and images. Native-text PDFs
  and DOCX don't need it.
- **Document text leaves the host.** OCR (for scans and images), extraction
  (DeepSeek or another OpenAI-compatible endpoint) and answering (Gemini) are
  external APIs. Embeddings and reranking are local.
- **DOCX has no page/bbox provenance**; typed facts carry a page but no bbox.
- **Bounding boxes are block-level**, not word-level, and only attached above
  50% token overlap.
- **Supported formats:** PDF, PNG, JPEG, DOCX.

## Takeaways for your own PDF RAG pipeline

1. Probe the text layer before OCR; use per-page thresholds to catch scans.
2. Normalize every engine's output to pages + blocks + polygons.
3. Put page markers in the extraction prompt so page numbers survive the LLM.
4. Attach regions by overlap with a threshold; prefer no highlight to a wrong one.
5. Never let the model emit sources directly: give it ids, validate them, and
   make "unsupported" a valid answer.

---

**About Filemindr.** Filemindr is an open-source (AGPL-3.0), self-hostable RAG and
document intelligence platform: OCR, structured extraction, hybrid retrieval
and agentic answers with page-level citations. Source:
<https://github.com/abby306/filemindr> · OCR docs:
<https://abby306.github.io/filemindr/features/ocr-document-processing/> ·
Citations: <https://abby306.github.io/filemindr/features/agentic-rag-citations/>
