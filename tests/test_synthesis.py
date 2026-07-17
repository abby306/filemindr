"""Agentic synthesis: the retrieve→reason→answer loop.

Both seams are stubbed — `synthesis._gemini_turn` (no Gemini API) and
`retrieval.retrieve` (no DB/models) — so the loop logic, citation grounding, the
search tool, and the bounded-iteration fallback are tested deterministically.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import synthesis
from app.services.retrieval import FactHit, RetrievalResult
from app.services.synthesis import ModelTurn


def _fact(key, text, *, fact_id=None, doc=None, page=1) -> FactHit:
    return FactHit(key=key, text=text, document_id=doc or uuid.uuid4(),
                   source="vector", page=page, fact_id=fact_id)


@pytest.fixture
def no_db(monkeypatch):
    """Make synthesize run without a real session, catalog, or doc-meta lookups.

    Also stubs the GPT-4o escalation seam to a no-op (returns no support) so the
    `supported=false` paths stay deterministic; escalation tests override it.
    """
    monkeypatch.setattr(synthesis, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(synthesis, "_load_doc_meta", lambda *a, **k: None)
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {"total_documents": 0, "documents": []},
    )
    monkeypatch.setattr(
        synthesis, "_openai_resynthesize",
        lambda query, candidates, history: {"supported": False, "answer": "", "cited_fact_ids": []},
    )


class _FakeSession:
    def close(self): ...


def _script(monkeypatch, turns: list[ModelTurn]):
    """Drive _gemini_turn through a fixed sequence of model decisions."""
    seq = iter(turns)
    monkeypatch.setattr(
        synthesis, "_gemini_turn",
        lambda transcript, *, allow_search, model: next(seq),
    )


def _stub_retrieve(monkeypatch, *result_facts: list[FactHit]):
    """Return a RetrievalResult per successive retrieve() call."""
    seq = iter(result_facts)
    def fake(query, account_id, *, db=None, k=5, **kwargs):
        facts = next(seq)
        return RetrievalResult(query=query, intent="semantic", facts=facts,
                               doc_ids=[f.document_id for f in facts])
    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake)


def test_finish_immediately_with_citation(no_db, monkeypatch) -> None:
    fid = uuid.uuid4()
    _stub_retrieve(monkeypatch, [_fact("k1", "The price is $20/month.", fact_id=fid, page=3)])
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            "answer": "It costs $20/month.", "cited_fact_ids": ["f1"], "supported": True,
        }),
    ])

    res = synthesis.synthesize("price?", uuid.uuid4())

    assert res.supported is True
    assert res.answer == "It costs $20/month."
    assert len(res.citations) == 1
    assert res.citations[0].fact_id == fid
    assert res.citations[0].page == 3
    assert res.searches == []


def test_search_then_finish(no_db, monkeypatch) -> None:
    # First pool is thin; the agent searches, then cites a fact from the 2nd pool.
    fid = uuid.uuid4()
    _stub_retrieve(
        monkeypatch,
        [_fact("k1", "Unrelated.")],                                  # initial pool
        [_fact("k2", "The VAT is PHP 20.25.", fact_id=fid, page=1)],  # after search
    )
    _script(monkeypatch, [
        ModelTurn(tool="search", args={"query": "VAT amount"}),
        ModelTurn(tool="finish", args={
            "answer": "The VAT is PHP 20.25.", "cited_fact_ids": ["f2"], "supported": True,
        }),
    ])

    res = synthesis.synthesize("what was the vat?", uuid.uuid4())

    assert res.searches == ["VAT amount"]
    assert res.candidates_seen == 2  # both pools registered
    assert [c.fact_id for c in res.citations] == [fid]


def test_hallucinated_citation_is_dropped(no_db, monkeypatch) -> None:
    _stub_retrieve(monkeypatch, [_fact("k1", "A fact.", fact_id=uuid.uuid4())])
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            "answer": "...", "cited_fact_ids": ["f1", "f99"],  # f99 was never offered
            "supported": True,
        }),
    ])

    res = synthesis.synthesize("q", uuid.uuid4())

    assert len(res.citations) == 1  # f99 dropped, only f1 kept


def test_unsupported_answer(no_db, monkeypatch) -> None:
    _stub_retrieve(monkeypatch, [_fact("k1", "Something irrelevant.")])
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            "answer": "The documents don't contain that.",
            "cited_fact_ids": [], "supported": False,
        }),
    ])

    res = synthesis.synthesize("unknowable?", uuid.uuid4())

    assert res.supported is False
    assert res.citations == []


def test_bounded_loop_forces_finish(no_db, monkeypatch) -> None:
    # Model keeps searching forever; the loop must terminate with an honest miss.
    _stub_retrieve(monkeypatch, *([[_fact(f"k{i}", "noise")] for i in range(10)]))
    monkeypatch.setattr(
        synthesis, "_gemini_turn",
        lambda transcript, *, allow_search, model: ModelTurn(tool="search", args={"query": "again"}),
    )

    res = synthesis.synthesize("q", uuid.uuid4(), max_steps=3)

    assert res.supported is False
    assert "couldn't find" in res.answer.lower()
    assert len(res.searches) <= 3  # bounded


def test_tokens_accumulate(no_db, monkeypatch) -> None:
    _stub_retrieve(monkeypatch, [_fact("k1", "x", fact_id=uuid.uuid4())], [_fact("k2", "y")])
    _script(monkeypatch, [
        ModelTurn(tool="search", args={"query": "more"}, prompt_tokens=100, completion_tokens=10),
        ModelTurn(tool="finish", args={"answer": "a", "cited_fact_ids": ["f1"], "supported": True},
                  prompt_tokens=150, completion_tokens=20),
    ])

    res = synthesis.synthesize("q", uuid.uuid4())

    assert res.prompt_tokens == 250
    assert res.completion_tokens == 30


def test_synthesize_iter_emits_step_events(no_db, monkeypatch) -> None:
    fid = uuid.uuid4()
    _stub_retrieve(
        monkeypatch,
        [_fact("k1", "Unrelated.")],
        [_fact("k2", "The VAT is PHP 20.25.", fact_id=fid)],
    )
    _script(monkeypatch, [
        ModelTurn(tool="search", args={"query": "VAT amount"}),
        ModelTurn(tool="finish", args={"answer": "PHP 20.25.", "cited_fact_ids": ["f2"], "supported": True}),
    ])

    events = list(synthesis.synthesize_iter("vat?", uuid.uuid4()))
    types = [e["type"] for e in events]

    # Real narration: candidates gathered, then a thinking beat before every
    # model turn — the client shows live progress instead of dead air.
    assert types == ["intent", "retrieved", "thinking", "searching", "thinking", "result"]
    assert events[0]["intent"] == "semantic"
    assert events[1]["found"] == 1  # the initial pool
    # Transparency payload: which documents matched + the matched key data.
    assert events[1]["sources"] == [{"title": "Untitled document", "facts": 1}]
    assert events[1]["highlights"] == ["Unrelated."]
    assert events[2]["step"] == 1
    searching = next(e for e in events if e["type"] == "searching")
    assert searching["query"] == "VAT amount"
    assert searching["highlights"] == ["The VAT is PHP 20.25."]
    assert events[-1]["result"].supported is True  # final result rides the last event


def test_escalation_adopts_gpt4o_when_flash_misses(no_db, monkeypatch) -> None:
    fid = uuid.uuid4()
    _stub_retrieve(monkeypatch, [_fact("k1", "The total is $1240.", fact_id=fid, page=2)])
    # Flash gives up...
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            "answer": "Not sure.", "cited_fact_ids": [], "supported": False,
        }),
    ])
    # ...but GPT-4o grounds it in the candidate we already had.
    seen = {}
    def fake_hard(query, candidates, history):
        seen["candidates"] = candidates
        return {"answer": "The total is $1240.", "cited_fact_ids": ["f1"],
                "supported": True, "_pt": 80, "_ct": 12}
    monkeypatch.setattr(synthesis, "_openai_resynthesize", fake_hard)

    res = synthesis.synthesize("total?", uuid.uuid4())

    assert res.escalated is True
    assert res.supported is True
    assert res.model == synthesis.HARD_MODEL
    assert [c.fact_id for c in res.citations] == [fid]  # validated through the registry
    assert seen["candidates"]  # the hard model saw the candidate pool


def test_escalation_keeps_unsupported_when_gpt4o_also_misses(no_db, monkeypatch) -> None:
    # no_db already stubs _openai_resynthesize → supported=False
    _stub_retrieve(monkeypatch, [_fact("k1", "Irrelevant.")])
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={"answer": "Can't find it.", "cited_fact_ids": [], "supported": False}),
    ])

    res = synthesis.synthesize("unknowable?", uuid.uuid4())

    assert res.supported is False
    assert res.escalated is False
    assert res.model == synthesis.MODEL


def test_escalation_failure_falls_back_to_flash_answer(no_db, monkeypatch) -> None:
    # Hard model is unavailable (e.g. rate limit / billing) — must NOT crash the answer.
    _stub_retrieve(monkeypatch, [_fact("k1", "A fact.", fact_id=uuid.uuid4())])
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={"answer": "Honest miss.", "cited_fact_ids": [], "supported": False}),
    ])
    def boom(query, candidates, history):
        raise RuntimeError("429 billing_not_active")
    monkeypatch.setattr(synthesis, "_openai_resynthesize", boom)

    res = synthesis.synthesize("q", uuid.uuid4())  # no exception

    assert res.supported is False
    assert res.escalated is False
    assert res.answer == "Honest miss."


# --- transient-error resilience on the Gemini seam ---------------------------


def test_is_transient_gemini_matrix() -> None:
    """Retry 429/5xx/timeouts; fail fast on real 4xx and unknown errors."""

    def with_code(code: int) -> Exception:
        exc = Exception("boom")
        exc.code = code  # duck-typed like google.genai.errors.APIError
        return exc

    assert synthesis._is_transient_gemini(with_code(429))
    assert synthesis._is_transient_gemini(with_code(503))
    assert synthesis._is_transient_gemini(with_code(500))
    assert synthesis._is_transient_gemini(TimeoutError())
    assert synthesis._is_transient_gemini(ConnectionError())
    assert not synthesis._is_transient_gemini(with_code(400))
    assert not synthesis._is_transient_gemini(with_code(401))
    assert not synthesis._is_transient_gemini(Exception("no code"))


def test_gemini_turn_survives_one_transient_failure(monkeypatch) -> None:
    """A mid-loop 503 used to kill the whole answer; now it retries through."""
    from types import SimpleNamespace

    calls = {"n": 0}

    class Transient(Exception):
        code = 503

    fake_resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=2),
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="finish", args={"answer": "ok"}
                            )
                        )
                    ]
                )
            )
        ],
        text="",
    )

    def generate_content(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Transient("503 mid-loop")
        return fake_resp

    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    monkeypatch.setattr(synthesis, "_get_client", lambda: fake_client)

    turn = synthesis._gemini_turn(
        [{"role": "user", "text": "q"}], allow_search=True, model="gemini-2.5-flash"
    )

    assert calls["n"] == 2
    assert turn.tool == "finish"
    assert turn.args == {"answer": "ok"}


# --- conversation-aware retrieval (follow-up anchoring) ----------------------


def test_contextual_query_builds_from_user_turns() -> None:
    assert synthesis._contextual_query("q", None) is None
    assert synthesis._contextual_query("q", [{"role": "assistant", "content": "hi"}]) is None

    history = [
        {"role": "user", "content": "meter data management db design"},
        {"role": "assistant", "content": "use a CustomerMeter table"},
        {"role": "user", "content": "customer and meter relations"},
    ]
    ctx = synthesis._contextual_query("what about the keys?", history)
    assert ctx.startswith("what about the keys? ")
    assert "meter data management" in ctx
    assert "customer and meter relations" in ctx
    assert "CustomerMeter" not in ctx  # assistant turns don't leak in

    capped = synthesis._contextual_query("q", [{"role": "user", "content": "x" * 1000}])
    assert len(capped) <= len("q ") + 240


def test_follow_up_anchors_previously_cited_documents(no_db, monkeypatch) -> None:
    """A vague follow-up whose words rank the WRONG document first still gets
    the previously-cited document's facts into the pool, citable by the model."""
    wrong_doc, right_doc = uuid.uuid4(), uuid.uuid4()
    right_fid = uuid.uuid4()

    calls = []

    def fake_retrieve(query, account_id, *, db=None, k=5, document_ids=None, **kw):
        calls.append({"query": query, "k": k, "document_ids": document_ids})
        if document_ids:  # the anchored pass, scoped to the cited doc
            facts = [_fact("r1", "CustomerMeter keys: meter_id, customer_id.",
                           fact_id=right_fid, doc=right_doc)]
        elif query.startswith("what about the keys?") and " meter" in query:
            facts = [_fact("c1", "Assignment history lives in CustomerMeter.", doc=right_doc)]
        else:  # the raw follow-up ranks the wrong doc first
            facts = [_fact("w1", "UUIDs are used for all primary keys.", doc=wrong_doc)]
        return RetrievalResult(query=query, intent="semantic", facts=facts,
                               doc_ids=[f.document_id for f in facts])

    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake_retrieve)
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            # Anchored facts lead the pool, so the cited doc's fact is f1.
            "answer": "meter_id + customer_id.", "cited_fact_ids": ["f1"], "supported": True,
        }),
    ])

    history = [
        {"role": "user", "content": "meter data management system db relations"},
        {"role": "assistant", "content": "via a CustomerMeter table"},
    ]
    res = synthesis.synthesize(
        "what about the keys?", uuid.uuid4(),
        history=history, anchor_document_ids=[right_doc],
    )

    # Three retrieval passes: raw query, anchored to the cited doc, contextual.
    assert [bool(c["document_ids"]) for c in calls] == [False, True, False]
    assert calls[1]["document_ids"] == [right_doc]
    assert "meter data management" in calls[2]["query"]
    # The pool held wrong-doc AND right-doc facts; the model cited the right one.
    assert res.citations[0].document_id == right_doc
    assert res.citations[0].fact_id == right_fid


def test_no_history_no_anchors_single_retrieval(no_db, monkeypatch) -> None:
    calls = []

    def fake_retrieve(query, account_id, *, db=None, k=5, document_ids=None, **kw):
        calls.append(query)
        return RetrievalResult(query=query, intent="semantic",
                               facts=[_fact("k1", "A fact.")], doc_ids=[])

    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake_retrieve)
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={"answer": "x", "cited_fact_ids": [], "supported": False}),
    ])
    synthesis.synthesize("plain question", uuid.uuid4())
    assert calls == ["plain question"]  # no extra passes without context


# --- read_page: recover detail that extraction dropped -----------------------


def test_read_page_registers_citable_page(no_db, monkeypatch) -> None:
    """When facts lack the detail, the agent reads the raw page and cites it
    (document + page, no fact id → page-level provenance)."""
    from app.services.catalog import CatalogDoc

    doc_id = uuid.uuid4()
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {
            "total_documents": 1,
            "documents": [CatalogDoc(document_id=doc_id, title="MDM Schema")],
        },
    )
    _stub_retrieve(monkeypatch, [_fact("k1", "The schema has 26 tables.", doc=doc_id)])
    monkeypatch.setattr(
        synthesis, "_page_text",
        lambda db, account_id, d, page: (
            "Meter table: PK meter_id UUID; FK customer_id → Customer."
            if (d == doc_id and page == 4)
            else None
        ),
    )
    _script(monkeypatch, [
        ModelTurn(tool="read_page", args={"document_ref": "d1", "page": 4}),
        ModelTurn(tool="finish", args={
            "answer": "Meter uses PK meter_id and FK customer_id.",
            "cited_fact_ids": ["f2"], "supported": True,  # f2 = the read page
        }),
    ])

    events = list(synthesis.synthesize_iter("what are the keys?", uuid.uuid4()))
    reading = next(e for e in events if e["type"] == "reading")
    assert reading["page"] == 4
    assert reading["found"] == 1

    result = events[-1]["result"]
    assert result.supported is True
    assert len(result.citations) == 1
    assert result.citations[0].document_id == doc_id
    assert result.citations[0].page == 4
    assert result.citations[0].fact_id is None  # page-level provenance


def test_read_page_unavailable_reports_and_continues(no_db, monkeypatch) -> None:
    from app.services.catalog import CatalogDoc

    doc_id = uuid.uuid4()
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {
            "total_documents": 1,
            "documents": [CatalogDoc(document_id=doc_id, title="MDM Schema")],
        },
    )
    _stub_retrieve(monkeypatch, [_fact("k1", "High-level only.", doc=doc_id)])
    monkeypatch.setattr(synthesis, "_page_text", lambda *a: None)
    _script(monkeypatch, [
        ModelTurn(tool="read_page", args={"document_ref": "d1", "page": 99}),
        ModelTurn(tool="finish", args={
            "answer": "The document doesn't detail that.",
            "cited_fact_ids": [], "supported": False,
        }),
    ])

    events = list(synthesis.synthesize_iter("keys?", uuid.uuid4()))
    reading = next(e for e in events if e["type"] == "reading")
    assert reading["found"] == 0
    assert events[-1]["result"].supported is False


# --- focus guard: off-focus finishes get one deterministic rejection ---------


def test_off_focus_unattributed_finish_is_rejected_once(no_db, monkeypatch) -> None:
    """Citing only a non-focus doc without naming it → rejected; the model then
    reads the focus doc's page and answers from it."""
    from app.services.catalog import CatalogDoc

    focus_doc, other_doc = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {
            "total_documents": 1,
            "documents": [CatalogDoc(document_id=focus_doc, title="MDM Schema")],
        },
    )
    # Initial pool: the tempting off-focus fact ranks first.
    def fake_retrieve(query, account_id, *, db=None, k=5, document_ids=None, **kw):
        if document_ids:  # anchored pass over the focus doc
            return RetrievalResult(query=query, intent="semantic",
                facts=[_fact("a1", "The schema groups 26 tables.", doc=focus_doc)],
                doc_ids=[focus_doc])
        return RetrievalResult(query=query, intent="semantic",
            facts=[_fact("w1", "UUIDs are used for all primary keys.", doc=other_doc)],
            doc_ids=[other_doc])

    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        synthesis, "_page_text",
        lambda db, account_id, d, page: "Meter: PK meter_id; FK customer_id." if d == focus_doc else None,
    )
    _script(monkeypatch, [
        # 1st attempt: supported answer citing ONLY the off-focus doc, unnamed.
        ModelTurn(tool="finish", args={
            "answer": "UUIDs for all primary keys.", "cited_fact_ids": ["f2"], "supported": True,
        }),
        # After rejection: read the focus doc's page, then answer from it.
        ModelTurn(tool="read_page", args={"document_ref": "d1", "page": 4}),
        ModelTurn(tool="finish", args={
            "answer": "Meter uses PK meter_id, FK customer_id.",
            "cited_fact_ids": ["f3"], "supported": True,
        }),
    ])

    events = list(synthesis.synthesize_iter(
        "what keys?", uuid.uuid4(),
        history=[{"role": "user", "content": "the mdm schema"}],
        anchor_document_ids=[focus_doc],
    ))
    result = events[-1]["result"]
    assert result.citations[0].document_id == focus_doc  # ended on the focus doc
    assert any(e["type"] == "reading" for e in events)


def test_off_focus_finish_accepted_when_it_names_the_document(no_db, monkeypatch) -> None:
    from app.services.catalog import CatalogDoc

    focus_doc, other_doc = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {
            "total_documents": 1,
            "documents": [CatalogDoc(document_id=focus_doc, title="MDM Schema")],
        },
    )
    def fake_retrieve(query, account_id, *, db=None, k=5, document_ids=None, **kw):
        facts = [_fact("w1", "UUIDs everywhere.", doc=other_doc)]
        return RetrievalResult(query=query, intent="semantic", facts=facts, doc_ids=[other_doc])
    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake_retrieve)
    # The other doc's title is known to the loop.
    def fake_load_meta(db, account_id, doc_ids, titles):
        titles[other_doc] = "StockSense Blueprint"
    monkeypatch.setattr(synthesis, "_load_doc_meta", fake_load_meta)
    _script(monkeypatch, [
        ModelTurn(tool="finish", args={
            "answer": "Your StockSense Blueprint uses UUIDs for all primary keys.",
            "cited_fact_ids": ["f1"], "supported": True,
        }),
    ])

    res = synthesis.synthesize(
        "what keys?", uuid.uuid4(),
        history=[{"role": "user", "content": "the mdm schema"}],
        anchor_document_ids=[focus_doc],
    )
    # Named the source → accepted on the first turn, no rejection loop.
    assert res.answer.startswith("Your StockSense Blueprint")
    assert res.citations[0].document_id == other_doc


def test_off_focus_double_down_gets_server_attribution(no_db, monkeypatch) -> None:
    """If the model repeats the off-focus finish after rejection, the server
    prefixes the attribution itself — misattribution can't reach the user."""
    from app.services.catalog import CatalogDoc

    focus_doc, other_doc = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        synthesis.catalog, "corpus_overview",
        lambda db, account_id: {
            "total_documents": 1,
            "documents": [CatalogDoc(document_id=focus_doc, title="MDM Schema")],
        },
    )
    def fake_retrieve(query, account_id, *, db=None, k=5, document_ids=None, **kw):
        facts = [_fact("w1", "UUIDs are used for all primary keys.", doc=other_doc)]
        return RetrievalResult(query=query, intent="semantic", facts=facts, doc_ids=[other_doc])
    monkeypatch.setattr(synthesis.retrieval, "retrieve", fake_retrieve)
    def fake_load_meta(db, account_id, doc_ids, titles):
        titles.setdefault(other_doc, "StockSense Blueprint")
        titles.setdefault(focus_doc, "MDM Schema")
    monkeypatch.setattr(synthesis, "_load_doc_meta", fake_load_meta)

    same_finish = ModelTurn(tool="finish", args={
        "answer": "UUIDs are used for all primary keys.",
        "cited_fact_ids": ["f1"], "supported": True,
    })
    _script(monkeypatch, [same_finish, same_finish])  # doubles down after rejection

    res = synthesis.synthesize(
        "what keys?", uuid.uuid4(),
        history=[{"role": "user", "content": "the mdm schema"}],
        anchor_document_ids=[focus_doc],
    )
    assert res.answer.startswith("Note: this comes from “StockSense Blueprint”")
    assert "MDM Schema" in res.answer  # names what it is NOT from, too
    assert res.answer.endswith("UUIDs are used for all primary keys.")
