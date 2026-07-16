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
- finish(answer, cited_fact_ids, supported): give the final answer.

Guidance:
- Use the conversation history to interpret follow-ups and corrections.
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
    return [types.Tool(function_declarations=[find, search, finish])]


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
    resp = _get_client().models.generate_content(
        model=model, contents=_to_contents(transcript), config=config
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
):
    """The agentic loop as an event stream (for SSE), ending in the final result.

    Yields step events — ``{"type": "intent"|"find_documents"|"searching"|
    "escalating", ...}`` — and finally ``{"type": "result", "result": SynthesisResult}``.
    `synthesize()` drains this; the streaming endpoint forwards the events. Same
    contract as `synthesize` otherwise (corpus overview + initial pool + history seed
    the model; bounded loop with a forced finish; `document_ids` pins retrieval).
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
        _load_doc_meta(db, account_id, [h.document_id for h in first.facts], titles)
        initial = facts.add(first.facts)

        payload = {
            "query": query, "intent": intent,
            "corpus": overview,
            "candidates": _fact_payload(initial, titles),
        }
        if document_ids:
            payload["scope"] = (
                "The user's question is scoped to a specific document; answer from it."
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

        for step in range(max_steps):
            allow_search = step < max_steps - 1  # force finish on the last turn
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
                yield {"type": "find_documents", "query": name, "found": len(added)}
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
                yield {"type": "searching", "query": rq, "found": len(added)}
                continue

            if turn.tool == "finish" or "answer" in turn.args:
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
) -> SynthesisResult:
    """Answer `query` for `account_id` via the corpus-aware agentic loop.

    Thin drain of `synthesize_iter` (the event-producing core) — same behavior, just
    discarding the step events and returning the final `SynthesisResult`.
    """
    result: SynthesisResult | None = None
    for event in synthesize_iter(
        query, account_id, db=db, history=history, model=model,
        max_steps=max_steps, document_ids=document_ids,
    ):
        if event["type"] == "result":
            result = event["result"]
    return result  # type: ignore[return-value]
