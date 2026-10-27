---
title: "Agentic RAG with Source Citations: Grounded Document Q&A"
nav_title: Agentic RAG & citations
description: "How Filemindr's agentic RAG loop answers questions over documents with tool calls, enforced citations, honest 'not found' answers and a live trace."
---

# Agentic RAG and source citations

Filemindr doesn't hand the language model a fixed top-k and hope. It runs a short **agentic RAG loop**: the model gets a candidate pool and tools, and decides whether to locate a document, search more narrowly or read a page before it commits to an answer. Every answer has to cite the facts it used. The implementation is [`app/services/synthesis.py`](https://github.com/abby306/filemindr/blob/main/app/services/synthesis.py).

![An answer combining an insurance policy and a lease, with both cited](../../../docs/assets/screenshots/agentic-answer-citations.webp)

## What the model sees

Each turn, Gemini 2.5 Flash receives:

- a bounded **corpus overview** (what documents exist: titles, classes, page counts)
- an initial **candidate pool** of 12 facts from [hybrid retrieval](hybrid-search.md), each with a short id (`f1`, `f2`, …), its document and page
- the **conversation history**, plus a note on which documents the conversation has been about, so follow-ups like "which of those is due first?" or "no, the other one" resolve correctly

## The tools

| Tool | Purpose |
|---|---|
| `find_documents(class, name, about, uploaded_after, uploaded_before)` | Resolve a human reference ("the NDA", "the March invoice", "what I uploaded last week") to real documents |
| `search(query, document_ref, class)` | Retrieve more candidate facts, optionally scoped to one document or class |
| `read_page(document_ref, page)` | Read the raw text of one page when the extracted facts don't have enough detail (table columns, exact wording). The page becomes a citable candidate |
| `finish(answer, cited_fact_ids, supported)` | Commit the final answer |

Function calling runs in `ANY` mode, so every turn is a structured tool call rather than free text. The loop is **bounded to 5 steps**, and on the last step the model must call `finish`.

## How citations are enforced

- The model can only cite ids **we gave it**. Unknown ids are dropped, and the remaining ones resolve to real `document_id`, `page` and, for atomic facts, `bbox`. A made-up citation can't reach the user.
- **`supported=false` is a first-class outcome.** If the documents don't contain the answer, the model says so plainly instead of drawing on outside knowledge. The system prompt forbids outside knowledge.
- **Focus guard.** If a follow-up answer cites only facts from a document unrelated to the conversation, without naming it, the answer is challenged once, so a fact from the wrong document isn't passed off as the answer.
- **Optional escalation.** When Flash finishes with `supported=false`, a single GPT-4o pass may re-reason over the same candidates. Its answer is adopted only if it is grounded in valid candidate ids. Any failure (no key, rate limit) is ignored and the honest "not found" answer stands.

![Clicking a citation opens the lease on page 2 with the cited clause highlighted](../../../docs/assets/screenshots/citation-provenance.webp)

## Streaming and the live trace

`POST /api/v1/conversations/{id}/messages/stream` streams Server-Sent Events: retrieval plan, documents looked up, searches issued, candidate facts, and finally the answer and citations. The web app shows these as a live trace ("Understanding the question → Gathering facts from your documents → Reading the top matches"). Each answer's full trace (plan, candidates, tokens, latency, model, escalation) is stored in `retrieval_traces` for analytics and debugging.

## Scoping a question

- Type **`@`** in the composer to point at specific documents (passed as `document_ids`).
- Use **Ask this folder** in the archive to restrict retrieval to one class and its subclasses (`class_slug`).
- Or ask in plain language ("in the lease, …"), and the agent uses `find_documents` and then a scoped `search`.

## Ratings feed evaluation

Users can rate each answer 👍 / 👎. Ratings are stored per message, show up in quality analytics (grounded-answer rate, latency), and can be turned into gold queries for the [`eval/`](https://github.com/abby306/filemindr/tree/main/eval) harness.

## Limits to know about

- Answering requires the **Gemini API**. There is no local-LLM answering path yet.
- The model writes the answer text. Citations are verified to be real candidates, but whether the prose faithfully reflects them depends on the model. Click through to check high-stakes answers.
- Retrieval and FTS are tuned for English.

Related: [Hybrid search](hybrid-search.md) · [Architecture](../architecture.md) · [FAQ](../faq.md)
