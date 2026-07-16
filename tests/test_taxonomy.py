"""Class taxonomy: routing reasons, hierarchical catalog, subclass expansion."""

from __future__ import annotations

import uuid

from app.db.models import Class
from app.db.session import SessionLocal
from app.services import extraction
from app.services.taxonomy import expand_class_slugs, get_or_create_class, slugify


def _classes(*pairs: tuple[str, float]) -> extraction.ExtractionResult:
    return extraction.ExtractionResult(
        classes=[extraction.ClassPrediction(slug=s, confidence=c) for s, c in pairs]
    )


# --- _route_status (pure) --------------------------------------------------
def test_route_no_class() -> None:
    assert extraction._route_status(extraction.ExtractionResult()) == ("needs_review", "no_class")


def test_route_low_confidence() -> None:
    assert extraction._route_status(_classes(("invoice", 0.3))) == ("needs_review", "low_confidence")


def test_route_confident_single() -> None:
    assert extraction._route_status(_classes(("invoice", 0.7))) == ("extracted", None)


def test_route_ambiguous_close_runner_up() -> None:
    # top 0.55, runner-up 0.50: within delta, runner-up above floor, top below ceiling.
    assert extraction._route_status(
        _classes(("invoice", 0.55), ("receipt", 0.50))
    ) == ("needs_review", "ambiguous")


def test_route_confident_top_trumps_close_runner_up() -> None:
    # top >= CONFIDENT_CEILING is trusted even with a close second.
    assert extraction._route_status(
        _classes(("invoice", 0.85), ("receipt", 0.80))
    ) == ("extracted", None)


def test_route_weak_runner_up_not_ambiguous() -> None:
    # runner-up below AMBIGUITY_FLOOR — a confident top with a weak second is fine.
    assert extraction._route_status(
        _classes(("invoice", 0.6), ("receipt", 0.2))
    ) == ("extracted", None)


def test_route_invalid_slug_only_goes_to_review() -> None:
    # A confident prediction under a non-catalog slug must not silently index the
    # doc classless — it routes to review instead.
    result = _classes(("financial", 1.0))  # not in the valid set below
    assert extraction._route_status(result, valid_slugs={"invoice", "receipt"}) == (
        "needs_review", "no_class",
    )
    # ...but a valid slug in the same set routes normally.
    assert extraction._route_status(
        _classes(("invoice", 0.9)), valid_slugs={"invoice"}
    ) == ("extracted", None)


# --- ClassPrediction slug normalization ------------------------------------
def test_slug_normalizer_recovers_path_and_arrow_shapes() -> None:
    assert extraction.ClassPrediction(slug="financial/invoice").slug == "invoice"
    assert extraction.ClassPrediction(slug="Financial > Invoice").slug == "invoice"
    assert extraction.ClassPrediction(slug="  Tax Form ").slug == "tax_form"
    assert extraction.ClassPrediction(slug="invoice").slug == "invoice"  # already clean


# --- _format_catalog (pure) ------------------------------------------------
def test_format_catalog_nests_children_under_parents() -> None:
    fin = Class(id=uuid.uuid4(), account_id=uuid.uuid4(), slug="financial", name="Financial", description="Money stuff")
    inv = Class(id=uuid.uuid4(), account_id=fin.account_id, slug="invoice", name="Invoice", description="A bill", parent_id=fin.id)
    text = extraction._format_catalog([inv, fin])
    lines = text.splitlines()
    assert lines[0] == "- financial: Money stuff"
    assert lines[1] == "    - invoice: A bill"  # indented under its parent


# --- expand_class_slugs (live DB) ------------------------------------------
def test_expand_parent_includes_children(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        parent = Class(account_id=acct, slug="money", name="Money", is_system=True)
        db.add(parent)
        db.flush()
        db.add_all([
            Class(account_id=acct, slug="bill", name="Bill", parent_id=parent.id, is_system=True),
            Class(account_id=acct, slug="rcpt", name="Receipt", parent_id=parent.id, is_system=True),
        ])
        db.commit()
        assert set(expand_class_slugs(db, acct, "money")) == {"money", "bill", "rcpt"}
        assert expand_class_slugs(db, acct, "bill") == ["bill"]  # leaf → itself
        assert expand_class_slugs(db, acct, "unknown") == ["unknown"]  # missing → itself


# --- get_or_create_class (live DB) -----------------------------------------
def test_get_or_create_reuses_existing(seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        first = get_or_create_class(db, acct, name="Field Notes")
        db.commit()
        again = get_or_create_class(db, acct, name="field  notes")  # same slug
        assert again.id == first.id
        assert slugify("Field Notes") == "field_notes"
