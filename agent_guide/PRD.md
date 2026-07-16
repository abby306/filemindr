# PRD.md — filemindr

Product requirements and scope. Living document; edit feature lines individually.

## Problem
People accumulate documents (invoices, IDs, contracts, receipts, reports) with no easy way to find or use what's inside them. Existing tools have weak retrieval and ignore the unglamorous edges.

## What it is
An intelligent document archivist. Users dump documents in; the system understands each one and answers questions over the whole archive with cited sources. Goal: a **common tool done excellently** — great retrieval, great UX — not a novel differentiator.

## Users
- **Personal account** — individual's own documents.
- **Company account** — shared company documents; any member can read/query/move (no roles yet).

## v1 goal
Establish the **core intelligence + retrieval engine** with high accuracy. Frontend polish is secondary.

## In scope (v1)
- Ingest: **web upload** (PDF, PNG/JPG, Word) and **email-in**.
- OCR when a PDF has no text layer; images always OCR'd.
- Per-document understanding: type/class (multi-label, incl. none), summary, typed facts/numbers, people/orgs/places, dates.
- User-defined classes in addition to ~10–15 predefined ones.
- Retrieval: chat Q&A over documents with **citations**; metadata filters; numeric queries.
- Accuracy measured by an eval harness (recall@k, answer correctness).

## Product surfaces (UI)
Apple-minimal web app; full spec in `FRONTEND.md` + the design-system PDF. Core surfaces:
- **Upload** — drag-drop any file; live pipeline progress (the "glimpse" of how a doc becomes structured data).
- **Document view** — summary, classification (with confidence), extracted key details, entities, dates, and provenance jump-to-source. Add/label custom classes here.
- **Ask** — GPT/Claude-style chat with a visible retrieval trace (tools/info retrieved) and click-to-source citations.
- **Ratings** — thumb + diagnostic reasons on each answer; feeds quality metrics and the eval harness.
- **Analytics** — usage (documents, queries, storage, token spend) and quality (rating %, grounded %, latency) dashboards.
- **Billing** — subscription tiers, usage-vs-quota meters, invoices, payment management.

### Phasing
- **v1 core:** Upload, Document view, Ask (the engine + its three primary surfaces) + ratings.
- **Fast-follow:** Analytics, Billing/subscriptions, quota enforcement.

## Monetization
Tiers map to real cost drivers — documents, queries, storage (the things that consume OCR/LLM/disk). Indicative: **Free** (small caps) → **Pro** (higher caps, priority OCR) → **Team** (company accounts, shared access, audit). Quotas surfaced as meters; upgrade is one calm step.

## Out of scope (v1 — later)
- Voice agent, WhatsApp ingestion, mobile scanner.
- PDF compilation / smart collections / checklist "what's missing".
- Expiry reminders, share links, form-filling.
- RBAC / granular permissions.

(Ratings, analytics, and billing are now in scope — see Product surfaces above.)

## Success criteria
- Documents reliably classified and structured; extraction is trustworthy (typed, cited).
- Chat answers are grounded — every claim cites a source; "not in your documents" when unsupported.
- Eval harness shows strong recall@k and answer correctness, and is run on every retrieval/prompt change.
- Token/cost kept low (cheap extraction tier, local embeddings).

## Non-negotiables
- Citations/provenance on every answer.
- Hard account isolation (no cross-account leakage).
- Encryption-at-rest and an access/audit trail for a corpus of IDs/financials/medical docs.
