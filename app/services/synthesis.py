"""Agentic synthesis — corpus-aware, conversational, grounded answers (Step 4 + chat).

The LLM isn't handed a fixed top-k. It gets a bounded **corpus overview**, an
initial candidate pool, the **conversation history**, and decision power via three
tools:

  * ``find_documents(...)`` — resolve a human reference ("the NDA", "March invoice",
    "the contract I uploaded last week") to real documents by class / name / upload
    window / semantic "about".
  * ``search(query, document_ref?, class?)`` — fact retrieval, optionally **scoped**
    to a document the agent found or a class the user named.
  * ``finish(answer, cited_fact_ids, supported)`` — commit the grounded answer.

So the agent decides: *find which document first, or go straight to facts?* — and a
follow-up turn carries the chat history so "no, the other one" works. The loop is
**bounded** (`_MAX_STEPS`) and forced to ``finish`` on the last step.

Grounding is enforced by construction: the model may only cite candidate ids we
handed it (hallucinated ids are dropped → real `document_id`/`page`/`bbox`);
`supported=false` is the honest "not in your documents" path; function-calling mode
is ANY, so every turn is a structured tool call.

`_gemini_turn` is the only network seam (Gemini 2.5 Flash) — tests stub it.
Everything is `account_id`-scoped through `retrieve` / `catalog`.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.retry import with_retry
from app.db.models import Document
from app.db.session import SessionLocal
from app.services import catalog, retrieval
from app.services.retrieval import FactHit

MODEL = "gemini-2.5-flash"
HARD_MODEL = "gpt-4o"  # escalation when the Flash loop can't ground an answer
_POOL_SIZE = 12  # candidates fetched per retrieval (initial + each tool search)
_MAX_STEPS = 5  # model turns: find/search a few times, then a forced finish

SYSTEM_PROMPT = """You are Filemindr's document assistant. Answer the user's \
question using ONLY the candidate facts and document summaries provided to you \
(facts have ids like "f3"; documents have ids like "d2"). Never use outside \
knowledge.

You are given a corpus overview (what documents exist), an initial set of candidate \
facts, and the conversation so far. You have three tools:
- find_documents(class, name, about, uploaded_after, uploaded_before): locate \
documents when the user refers to one you don't have facts for yet — by class \
(e.g. "invoice", "contract"), a name they remember, an upload date window, or a \
semantic "about" description. Returns document cards (with ids like d2).
- search(query, document_ref, class): retrieve more candidate facts. Pass \
document_ref (e.g. "d2") or class to scope the search to a specific document or \
group the user pointed at.
- read_page(document_ref, page): read the raw text of one page. Use it when the \
extracted facts lack the detail the user asks for — table columns, key \
definitions, exact wording, itemized lists. Facts show their page numbers and \
document cards show page counts; the returned page is a citable candidate.
- finish(answer, cited_fact_ids, supported): give the final answer.

Guidance:
- Use the conversation history to interpret follow-ups and corrections.
- A follow-up question is usually still about the document(s) you cited in \
your previous answers (when provided, "conversation_focus" names them). Answer \
follow-ups from those documents' facts, using search(document_ref=...) to dig \
deeper there. If those documents' facts do not contain the requested detail, \
read the relevant pages with read_page before concluding it is absent; only \
then SAY SO plainly (e.g. "the schema reference doesn't list key columns"). \
Never present \
a fact from an unrelated document as if it answered a question about the \
conversation's document — if you bring in another document's fact, name that \
document explicitly in the answer.
- If the user names or hints at a document, use find_documents, then search scoped \
to it.
- Ground every claim in provided facts/summaries. cited_fact_ids MUST be ids from \
the candidates.
- If the documents don't contain the answer, finish with supported=false and say so \
(cited_fact_ids may be empty).
- Be concise and specific; include actual values/names. Don't over-search."""


# --- result types ----------------------------------------------------------


@dataclass
class Citation:
    fact_id: uuid.UUID | None  # atomic-fact id (None for a structured-fact citation)
    document_id: uuid.UUID
    title: str | None
    page: int | None


@dataclass
class SynthesisResult:
    query: str
    answer: str
    supported: bool
    citations: list[Citation] = field(default_factory=list)
    intent: str = ""
    searches: list[str] = field(default_factory=list)  # follow-up queries issued
    documents_looked_up: list[str] = field(default_factory=list)  # find_documents queries
    candidates_seen: int = 0
    escalated: bool = False  # answered by the hard model (GPT-4o) after a Flash miss
    model: str = MODEL
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    candidate_facts: list[dict] = field(default_factory=list)  # all facts the model saw (trace)
    plan: dict = field(default_factory=dict)  # retrieval plan + searches (trace)


@dataclass
class ModelTurn:
    """One normalized model decision (provider-agnostic, so the loop is testable)."""

    tool: str | None  # "find_documents" | "search" | "finish" | None
    args: dict = field(default_factory=dict)
    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


# --- registries (short ids the model sees; resolve to real rows) ------------


class _FactRegistry:
    """Stable short ids (f1, f2, …) for facts across the loop → real FactHits."""

    def __init__(self) -> None:
        self._by_id: dict[str, FactHit] = {}
        self._by_key: dict[str, str] = {}
        self._n = 0

    def add(self, hits: list[FactHit]) -> list[tuple[str, FactHit]]:
        added = []
        for hit in hits:
            if hit.key in self._by_key:
                continue
            self._n += 1
            short = f"f{self._n}"
            self._by_id[short] = hit
            self._by_key[hit.key] = short
            added.append((short, hit))
        return added

    def id_for_key(self, key: str) -> str | None:
        return self._by_key.get(key)

    def get(self, short_id: str) -> FactHit | None:
        return self._by_id.get(short_id)

    def items(self) -> list[tuple[str, FactHit]]:
        """All (short_id, hit) pairs seen so far — for the trace candidate dump."""
        return list(self._by_id.items())

    def __len__(self) -> int:
        return len(self._by_id)


class _DocRegistry:
    """Stable short ids (d1, d2, …) for documents → real document ids."""

    def __init__(self) -> None:
        self._by_id: dict[str, uuid.UUID] = {}
        self._by_doc: dict[uuid.UUID, str] = {}
        self._n = 0

    def add(self, docs: list[catalog.CatalogDoc]) -> list[tuple[str, catalog.CatalogDoc]]:
        added = []
        for doc in docs:
            if doc.document_id in self._by_doc:
                continue
            self._n += 1
            short = f"d{self._n}"
            self._by_id[short] = doc.document_id
            self._by_doc[doc.document_id] = short
            added.append((short, doc))
        return added

    def resolve(self, short_id: str) -> uuid.UUID | None:
        return self._by_id.get(str(short_id))


# --- the network seam (Gemini) ---------------------------------------------

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from google import genai

                _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def _tools(allow_search: bool):
    from google.genai import types

    S = types.Schema
    finish = types.FunctionDeclaration(
        name="finish",
        description="Produce the final grounded answer with citations.",
        parameters=S(
            type=types.Type.OBJECT,
            properties={
                "answer": S(type=types.Type.STRING),
                "cited_fact_ids": S(type=types.Type.ARRAY, items=S(type=types.Type.STRING)),
                "supported": S(type=types.Type.BOOLEAN),
            },
            required=["answer", "cited_fact_ids", "supported"],
        ),
    )
    if not allow_search:
        return [types.Tool(function_declarations=[finish])]

    search = types.FunctionDeclaration(
        name="search",
        description="Retrieve more candidate facts; scope with document_ref or class.",
        parameters=S(
            type=types.Type.OBJECT,
            properties={
                "query": S(type=types.Type.STRING),
                "document_ref": S(type=types.Type.STRING, description="e.g. 'd2'"),
                "class": S(type=types.Type.STRING, description="class slug, e.g. 'invoice'"),
            },
            required=["query"],
        ),
    )
    find = types.FunctionDeclaration(
        name="find_documents",
        description="Locate documents by class, remembered name, upload date window, "
        "or a semantic 'about' description.",
        parameters=S(
            type=types.Type.OBJECT,
            properties={
                "class": S(type=types.Type.STRING),
                "name": S(type=types.Type.STRING),
                "about": S(type=types.Type.STRING),
                "uploaded_after": S(type=types.Type.STRING, description="YYYY-MM-DD"),
                "uploaded_before": S(type=types.Type.STRING, description="YYYY-MM-DD"),
            },
        ),
    )
    read_page = types.FunctionDeclaration(
        name="read_page",
        description="Read the raw text of one page of a document — use when the "
        "extracted facts lack the requested detail (table columns, key "
        "definitions, exact wording, lists). The page becomes a citable "
        "candidate.",
        parameters=S(
            type=types.Type.OBJECT,
            properties={
                "document_ref": S(type=types.Type.STRING, description="e.g. 'd2'"),
                "page": S(type=types.Type.INTEGER, description="1-based page number"),
            },
            required=["document_ref", "page"],
        ),
    )
    return [types.Tool(function_declarations=[find, search, read_page, finish])]


def _to_contents(transcript: list[dict]):
    from google.genai import types

    contents = []
    for e in transcript:
        if "response" in e:  # a tool result we fed back
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=e["name"], response=e["response"])],
            ))
        elif "tool" in e:  # the model's function call
            contents.append(types.Content(
                role="model",
                parts=[types.Part.from_function_call(name=e["tool"], args=e["args"])],
            ))
        else:  # plain text (conversation history or the current query payload)
            contents.append(types.Content(role=e["role"], parts=[types.Part(text=e["text"])]))
    return contents


def _is_transient_gemini(exc: Exception) -> bool:
    """True for Gemini/transport errors worth retrying (429/5xx/timeouts).

    Duck-typed on the status code (`google.genai.errors.APIError.code`) so a
    provider-side hiccup mid-way through the agentic loop doesn't kill the
    whole answer; real 4xx (auth, bad request) still fails fast.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (408, 429, 500, 502, 503, 504)


def _gemini_turn(transcript: list[dict], *, allow_search: bool, model: str) -> ModelTurn:
    """Run one model turn and normalize the result to a `ModelTurn` (the seam)."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0,
        tools=_tools(allow_search),
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
            )
        ),
    )
    settings = get_settings()
    resp = with_retry(
        lambda: _get_client().models.generate_content(
            model=model, contents=_to_contents(transcript), config=config
        ),
        attempts=settings.retry_max_attempts,
        base_delay=settings.retry_base_delay,
        is_retryable=_is_transient_gemini,
    )
    usage = resp.usage_metadata
    pt = getattr(usage, "prompt_token_count", 0) or 0
    ct = getattr(usage, "candidates_token_count", 0) or 0
    for part in resp.candidates[0].content.parts:
        if getattr(part, "function_call", None):
            fc = part.function_call
            return ModelTurn(tool=fc.name, args=dict(fc.args or {}),
                             prompt_tokens=pt, completion_tokens=ct)
    return ModelTurn(tool=None, text=resp.text or "", prompt_tokens=pt, completion_tokens=ct)


# --- hard-synthesis escalation (GPT-4o, single-shot) -----------------------

_openai_client_singleton = None
_openai_lock = threading.Lock()

_HARD_SYSTEM = (
    "You are a careful document QA assistant. Answer the question using ONLY the "
    "candidate facts provided (each has an id like 'f3'). Never use outside knowledge. "
    "Cite the facts you used. If the facts don't contain the answer, set supported=false "
    "and say so. Respond as JSON: {\"answer\": str, \"cited_fact_ids\": [str], "
    "\"supported\": bool}."
)


def _openai_client():
    global _openai_client_singleton
    if _openai_client_singleton is None:
        with _openai_lock:
            if _openai_client_singleton is None:
                from openai import OpenAI

                _openai_client_singleton = OpenAI(api_key=get_settings().openai_api_key)
    return _openai_client_singleton


def _openai_resynthesize(query: str, candidates: list[dict], history: list[dict] | None) -> dict:
    """One GPT-4o pass over the candidate facts → ``{answer, cited_fact_ids, supported}``.

    The escalation seam: a second, stronger opinion when Flash couldn't ground an
    answer. No tools — it only re-reasons over facts we already retrieved. Tests stub
    this so the suite stays offline. ``_pt``/``_ct`` carry token usage for the trace.
    """
    facts_block = "\n".join(
        f'{c["id"]}: {c["text"]} (document: {c["document"]}, page {c["page"]})'
        for c in candidates
    )
    convo = ""
    if history:
        convo = "Conversation so far:\n" + "\n".join(
            f'{t["role"]}: {t["content"]}' for t in history
        ) + "\n\n"
    user = f"{convo}Question: {query}\n\nCandidate facts:\n{facts_block}"
    resp = _openai_client().chat.completions.create(
        model=HARD_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _HARD_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    raw = json.loads(resp.choices[0].message.content or "{}")
    usage = resp.usage
    raw["_pt"] = getattr(usage, "prompt_tokens", 0) or 0
    raw["_ct"] = getattr(usage, "completion_tokens", 0) or 0
    return raw


# --- payload shaping -------------------------------------------------------


def _fact_payload(added: list[tuple[str, FactHit]], titles: dict) -> list[dict]:
    return [
        {
            "id": short, "text": hit.text, "source": hit.source,
            "score": round(hit.score, 3),
            "document": titles.get(hit.document_id) or str(hit.document_id),
            "page": hit.page,
        }
        for short, hit in added
    ]


def _doc_payload(added: list[tuple[str, catalog.CatalogDoc]]) -> list[dict]:
    return [
        {
            "ref": short, "title": doc.title,
            "class": doc.class_slugs[0] if doc.class_slugs else None,
            "uploaded": doc.created_at.date().isoformat() if doc.created_at else None,
            "summary": doc.summary,
        }
        for short, doc in added
    ]


_PAGE_TEXT_CHARS = 4000


def _page_text(db, account_id: uuid.UUID, document_id: uuid.UUID, page: int) -> str | None:
    """Raw text of one page (from the OCR-cache artifact), or None.

    The read_page tool's seam: extraction distills a document into facts, but
    dense reference material (schema tables, column lists) loses its detail —
    reading the actual page recovers it. Account-scoped; None for a foreign or
    unknown document, a missing cache artifact, or an empty/out-of-range page.
    """
    from app.services import ocr as ocr_service

    document = db.get(Document, document_id)
    if document is None or document.account_id != account_id:
        return None
    cached = ocr_service.load_cached_ocr(document.file_hash)
    if cached is None:
        return None
    for p in cached.pages:
        if p.page == page:
            text = " ".join(p.text.split()) if p.text else ""
            return text[:_PAGE_TEXT_CHARS] or None
    return None


def _contextual_query(query: str, history: list[dict] | None, *, max_turns: int = 2, max_chars: int = 240) -> str | None:
    """The query augmented with recent user turns, for a second retrieval pass.

    A follow-up like "what about the keys?" carries none of the conversation's
    vocabulary, so raw retrieval drifts to whatever document happens to match
    those words. Folding the last user turns back in pulls the conversation's
    actual subject into the candidate pool. None when there is no usable
    context (no history → no second pass).
    """
    if not history:
        return None
    prior = [
        t.get("content", "").strip()
        for t in history
        if t.get("role") == "user" and t.get("content", "").strip()
    ]
    if not prior:
        return None
    context = " ".join(prior[-max_turns:])[:max_chars].strip()
    return f"{query} {context}" if context else None


def _merge_hits(*hit_lists, cap: int) -> list:
    """Concatenate hit lists, dedupe by hit key, keep first-seen order, cap."""
    seen: set[str] = set()
    merged = []
    for hits in hit_lists:
        for h in hits:
            if h.key in seen:
                continue
            seen.add(h.key)
            merged.append(h)
            if len(merged) >= cap:
                return merged
    return merged


def _source_summary(hits, titles, *, max_docs: int = 4, max_highlights: int = 3) -> dict:
    """Display-ready transparency payload for a retrieval step: which documents
    matched (title + per-doc hit count, best first) and a few of the matched
    fact snippets — the SSE narration shows the user exactly what was read."""
    counts: dict[uuid.UUID, int] = {}
    for h in hits:
        counts[h.document_id] = counts.get(h.document_id, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    highlights: list[str] = []
    for h in hits[:max_highlights]:
        text = " ".join((h.text or "").split())
        if text:
            highlights.append(text[:110] + ("…" if len(text) > 110 else ""))
    return {
        "sources": [
            {"title": titles.get(doc_id) or "Untitled document", "facts": n}
            for doc_id, n in ordered[:max_docs]
        ],
        "more_documents": max(0, len(ordered) - max_docs),
        "highlights": highlights,
    }


def _load_doc_meta(db, account_id, doc_ids, titles) -> None:
    """Cache title for document ids not seen yet (account-scoped)."""
    for d in [d for d in doc_ids if d not in titles]:
        doc = db.get(Document, d)
        titles[d] = (doc.title or doc.original_filename) if (doc and doc.account_id == account_id) else None


def _parse_date(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def _build_result(args, facts, titles, *, query, intent, searches, lookups,
                  model, pt, ct, started) -> SynthesisResult:
    """Validate the model's citations against the registry and assemble the result."""
    citations, seen = [], set()
    for short in args.get("cited_fact_ids", []) or []:
        hit = facts.get(str(short))
        if hit is None or hit.key in seen:  # drop hallucinated / duplicate ids
            continue
        seen.add(hit.key)
        citations.append(Citation(
            fact_id=hit.fact_id, document_id=hit.document_id,
            title=titles.get(hit.document_id), page=hit.page,
        ))
    return SynthesisResult(
        query=query, answer=args.get("answer", "") or "",
        supported=bool(args.get("supported", False)), citations=citations,
        intent=intent, searches=searches, documents_looked_up=lookups,
        candidates_seen=len(facts), model=model,
        prompt_tokens=pt, completion_tokens=ct,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


# --- public entry point ----------------------------------------------------


def _candidate_dump(facts: _FactRegistry, titles: dict) -> list[dict]:
    """Every fact the model saw, shaped for the retrieval trace."""
    return _fact_payload(facts.items(), titles)


def _try_escalate(
    query: str, facts: _FactRegistry, titles: dict, history: list[dict] | None,
    prev: SynthesisResult, started: float,
) -> SynthesisResult | None:
    """Single-shot GPT-4o re-synthesis over the candidate pool; adopt only if grounded.

    Returns a new `SynthesisResult` when the hard model finds support, else None (so
    the honest `supported=false` answer stands). Reuses the citation registry, so its
    cited ids are validated exactly like the Flash path.
    """
    candidates = _candidate_dump(facts, titles)
    if not candidates:
        return None
    try:
        raw = _openai_resynthesize(query, candidates, history)
    except Exception:
        # Escalation is best-effort: if the hard model is unavailable (rate limit,
        # network, billing), keep the honest Flash `supported=false` answer rather
        # than failing the whole request.
        return None
    if not raw or not raw.get("supported"):
        return None
    result = _build_result(
        raw, facts, titles, query=query, intent=prev.intent, searches=prev.searches,
        lookups=prev.documents_looked_up, model=HARD_MODEL,
        pt=prev.prompt_tokens + (raw.get("_pt") or 0),
        ct=prev.completion_tokens + (raw.get("_ct") or 0), started=started,
    )
    result.escalated = True
    result.candidate_facts = prev.candidate_facts
    result.plan = prev.plan
    return result


def synthesize_iter(
    query: str,
    account_id: uuid.UUID,
    *,
    db=None,
    history: list[dict] | None = None,
    model: str = MODEL,
    max_steps: int = _MAX_STEPS,
    document_ids: list[uuid.UUID] | None = None,
    anchor_document_ids: list[uuid.UUID] | None = None,
):
    """The agentic loop as an event stream (for SSE), ending in the final result.

    Yields step events — ``{"type": "intent"|"retrieved"|"thinking"|
    "find_documents"|"searching"|"escalating", ...}`` — and finally
    ``{"type": "result", "result": SynthesisResult}``. The narration is real,
    not decorative: `retrieved` fires once the initial candidate pool is
    gathered, and `thinking` before every model turn (the otherwise-silent
    seconds), so a client can show live progress the whole way. `synthesize()`
    drains this; the streaming endpoint forwards the events. Same contract as
    `synthesize` otherwise (corpus overview + initial pool + history seed the
    model; bounded loop with a forced finish; `document_ids` pins retrieval).
    """
    started = time.monotonic()
    own_session = db is None
    db = db or SessionLocal()
    try:
        facts = _FactRegistry()
        docs = _DocRegistry()
        titles: dict[uuid.UUID, str | None] = {}

        overview = catalog.corpus_overview(db, account_id)
        overview_docs = docs.add(overview.pop("documents"))
        overview["documents"] = _doc_payload(overview_docs)
        corpus_doc_count = overview.get("total_documents", len(overview_docs))

        first = retrieval.retrieve(
            query, account_id, db=db, k=_POOL_SIZE, document_ids=document_ids
        )
        intent = first.intent
        yield {"type": "intent", "intent": intent}

        # Conversation-aware pool: a follow-up's raw words often point at the
        # wrong document. Anchor on the docs cited in the previous answer and
        # add a context-augmented retrieval pass, so the conversation's actual
        # subject is always represented among the candidates — anchored facts
        # FIRST (models weight early candidates heavily). (Skipped for
        # document-scoped chats — the scope already pins retrieval.)
        pool = list(first.facts)
        if document_ids is None:
            anchored_facts = []
            if anchor_document_ids:
                anchored = retrieval.retrieve(
                    query, account_id, db=db, k=8, document_ids=anchor_document_ids
                )
                anchored_facts = anchored.facts
            pool = _merge_hits(anchored_facts, pool, cap=_POOL_SIZE + 8)
            ctx_query = _contextual_query(query, history)
            if ctx_query:
                contextual = retrieval.retrieve(
                    ctx_query, account_id, db=db, k=_POOL_SIZE
                )
                pool = _merge_hits(pool, contextual.facts, cap=_POOL_SIZE + 8)

        _load_doc_meta(db, account_id, [h.document_id for h in pool], titles)
        initial = facts.add(pool)
        yield {
            "type": "retrieved",
            "found": len(initial),
            "documents": len({h.document_id for h in pool}),
            **_source_summary(pool, titles),
        }

        payload = {
            "query": query, "intent": intent,
            "corpus": overview,
            "candidates": _fact_payload(initial, titles),
        }
        if document_ids:
            payload["scope"] = (
                "The user's question is scoped to a specific document; answer from it."
            )
        elif anchor_document_ids:
            anchor_titles = [
                titles[d] for d in anchor_document_ids if titles.get(d)
            ]
            if anchor_titles:
                payload["conversation_focus"] = (
                    "This conversation is about: "
                    + "; ".join(anchor_titles)
                    + ". Answer the follow-up from these documents' facts. If "
                    "they don't contain the answer, say so plainly. Do not "
                    "substitute facts from other documents without explicitly "
                    "naming the other document in your answer."
                )
        transcript: list[dict] = [
            {"role": "model" if t["role"] == "assistant" else "user", "text": t["content"]}
            for t in (history or [])
        ]
        transcript.append({"role": "user", "text": json.dumps(payload, ensure_ascii=False, default=str)})

        searches: list[str] = []
        lookups: list[str] = []
        pt = ct = 0
        result: SynthesisResult | None = None
        off_focus_rejected = False  # the focus guard fires at most once

        for step in range(max_steps):
            allow_search = step < max_steps - 1  # force finish on the last turn
            yield {"type": "thinking", "step": step + 1}
            turn = _gemini_turn(transcript, allow_search=allow_search, model=model)
            pt += turn.prompt_tokens
            ct += turn.completion_tokens
            transcript.append({"role": "model", "tool": turn.tool or "finish", "args": turn.args})

            if turn.tool == "find_documents" and allow_search:
                name = (turn.args.get("name") or turn.args.get("about")
                        or turn.args.get("class") or "filter")
                lookups.append(name)
                found = catalog.find_documents(
                    db, account_id,
                    class_slug=turn.args.get("class"),
                    name=turn.args.get("name"),
                    about=turn.args.get("about"),
                    uploaded_after=_parse_date(turn.args.get("uploaded_after")),
                    uploaded_before=_parse_date(turn.args.get("uploaded_before")),
                )
                added = docs.add(found)
                transcript.append({"role": "tool", "name": "find_documents",
                                   "response": {"documents": _doc_payload(added)}})
                yield {
                    "type": "find_documents",
                    "query": name,
                    "found": len(added),
                    "sources": [
                        {"title": d.title or "Untitled document"} for d in found[:4]
                    ],
                }
                continue

            if turn.tool == "search" and allow_search:
                rq = (turn.args.get("query") or "").strip()
                searches.append(rq)
                ref = turn.args.get("document_ref")
                doc_id = docs.resolve(ref) if ref else None
                res = retrieval.retrieve(
                    rq, account_id, db=db, k=_POOL_SIZE,
                    document_ids=[doc_id] if doc_id else None,
                    class_slug=turn.args.get("class"),
                )
                _load_doc_meta(db, account_id, [h.document_id for h in res.facts], titles)
                added = facts.add(res.facts)
                transcript.append({"role": "tool", "name": "search",
                                   "response": {"candidates": _fact_payload(added, titles)}})
                yield {
                    "type": "searching",
                    "query": rq,
                    "found": len(added),
                    **_source_summary(res.facts, titles),
                }
                continue

            if turn.tool == "read_page" and allow_search:
                ref = turn.args.get("document_ref")
                try:
                    page_no = int(turn.args.get("page") or 0)
                except (TypeError, ValueError):
                    page_no = 0
                doc_id = docs.resolve(ref) if ref else None
                text = (
                    _page_text(db, account_id, doc_id, page_no)
                    if doc_id is not None and page_no >= 1
                    else None
                )
                if doc_id is not None:
                    _load_doc_meta(db, account_id, [doc_id], titles)
                title = (titles.get(doc_id) if doc_id else None) or "the document"
                if text is None:
                    transcript.append({"role": "tool", "name": "read_page",
                                       "response": {"error": "That page's text is not available."}})
                    yield {"type": "reading", "document": title, "page": page_no, "found": 0}
                    continue
                hit = FactHit(
                    key=f"page:{doc_id}:{page_no}", text=text,
                    document_id=doc_id, source="page", page=page_no,
                )
                facts.add([hit])
                short = facts.id_for_key(hit.key)
                transcript.append({"role": "tool", "name": "read_page",
                                   "response": {"candidates": [
                                       {"id": short, "document": title,
                                        "page": page_no, "text": text}
                                   ]}})
                yield {"type": "reading", "document": title, "page": page_no, "found": 1}
                continue

            if turn.tool == "finish" or "answer" in turn.args:
                # Focus guard (deterministic, once): a supported answer whose
                # citations are ALL outside the conversation's documents, and
                # which never names the other document, is a misattribution —
                # the exact failure mode where a follow-up about doc A gets
                # answered with doc B's fact as if it were A's. Reject it and
                # make the model choose an honest path. Skipped on the forced
                # final turn (nothing could follow a rejection).
                if (
                    allow_search
                    and not off_focus_rejected
                    and anchor_document_ids
                    and not document_ids
                    and turn.args.get("supported")
                ):
                    cited_docs = {
                        facts.get(cid).document_id
                        for cid in (turn.args.get("cited_fact_ids") or [])
                        if facts.get(cid) is not None
                    }
                    answer_lower = str(turn.args.get("answer") or "").lower()
                    names_cited_doc = any(
                        (titles.get(d) or "").lower() in answer_lower
                        for d in cited_docs
                        if titles.get(d)
                    )
                    if cited_docs and cited_docs.isdisjoint(set(anchor_document_ids)) and not names_cited_doc:
                        off_focus_rejected = True
                        transcript.append({
                            "role": "tool", "name": "finish",
                            "response": {"rejected": (
                                "Every citation is from a document OUTSIDE the "
                                "conversation focus, and the answer does not name "
                                "that document. Do ONE of: (1) answer from the "
                                "conversation's documents — use read_page("
                                "document_ref, page) if their facts lack the "
                                "detail; (2) state plainly that the conversation's "
                                "documents don't contain it; (3) keep the fact but "
                                "explicitly name its source document in the answer."
                            )},
                        })
                        continue
                result = _build_result(turn.args, facts, titles, query=query, intent=intent,
                                       searches=searches, lookups=lookups, model=model,
                                       pt=pt, ct=ct, started=started)
                break
            break  # model failed to finish (e.g. searched on the forced-finish turn)

        if result is None:
            result = SynthesisResult(
                query=query,
                answer="I couldn't find enough information in your documents to answer that.",
                supported=False, intent=intent, searches=searches, documents_looked_up=lookups,
                candidates_seen=len(facts), model=model, prompt_tokens=pt, completion_tokens=ct,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        result.candidate_facts = _candidate_dump(facts, titles)
        result.plan = {**first.plan, "searches": searches}
        result.plan["corpus_documents"] = corpus_doc_count

        if not result.supported:
            yield {"type": "escalating", "model": HARD_MODEL}
            escalated = _try_escalate(query, facts, titles, history, result, started)
            if escalated is not None:
                result = escalated

        yield {"type": "result", "result": result}
    finally:
        if own_session:
            db.close()


def synthesize(
    query: str,
    account_id: uuid.UUID,
    *,
    db=None,
    history: list[dict] | None = None,
    model: str = MODEL,
    max_steps: int = _MAX_STEPS,
    document_ids: list[uuid.UUID] | None = None,
    anchor_document_ids: list[uuid.UUID] | None = None,
) -> SynthesisResult:
    """Answer `query` for `account_id` via the corpus-aware agentic loop.

    Thin drain of `synthesize_iter` (the event-producing core) — same behavior, just
    discarding the step events and returning the final `SynthesisResult`.
    """
    result: SynthesisResult | None = None
    for event in synthesize_iter(
        query, account_id, db=db, history=history, model=model,
        max_steps=max_steps, document_ids=document_ids,
        anchor_document_ids=anchor_document_ids,
    ):
        if event["type"] == "result":
            result = event["result"]
    return result  # type: ignore[return-value]
