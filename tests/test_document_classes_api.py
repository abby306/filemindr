"""Human-in-the-loop class assignment: POST /documents/{id}/classes."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Class, Document, DocumentClass
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(seeded_account, *, account="personal_id") -> dict:
    return {
        "Authorization": f"Bearer {seeded_account['user_id']}",
        "X-Account-Id": str(seeded_account[account]),
    }


def _make_review_doc(acct, *, model_class_slug="invoice") -> tuple[uuid.UUID, uuid.UUID]:
    """A needs_review document with one model-assigned class guess."""
    with SessionLocal() as db:
        cls = Class(account_id=acct, slug=model_class_slug, name=model_class_slug.title(), is_system=True)
        doc = Document(
            account_id=acct, source="web_upload", original_filename="d.pdf",
            file_hash=uuid.uuid4().hex, storage_path="/tmp/d.pdf",
            status="needs_review", review_reason="ambiguous",
        )
        db.add_all([cls, doc])
        db.flush()
        db.add(DocumentClass(
            account_id=acct, document_id=doc.id, class_id=cls.id,
            confidence=0.5, assigned_by="model",
        ))
        db.commit()
        return doc.id, cls.id


def test_assign_existing_class_clears_review_and_indexes(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, class_id = _make_review_doc(acct)

    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(class_id)]},
    )
    assert res.status_code == 200
    card = res.json()
    assert card["status"] == "indexed"
    assert card["review_reason"] is None
    assert len(card["classes"]) == 1
    assert card["classes"][0]["assigned_by"] == "user"

    with SessionLocal() as db:
        rows = db.query(DocumentClass).filter_by(document_id=doc_id).all()
        assert [r.assigned_by for r in rows] == ["user"]


def test_assign_replaces_model_guesses(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, _ = _make_review_doc(acct, model_class_slug="receipt")
    with SessionLocal() as db:
        chosen = Class(account_id=acct, slug="contract", name="Contract", is_system=True)
        db.add(chosen)
        db.commit()
        chosen_id = chosen.id

    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(chosen_id)]},
    )
    assert res.status_code == 200
    slugs = {c["slug"] for c in res.json()["classes"]}
    assert slugs == {"contract"}  # the model's receipt guess is gone


def test_assign_inline_new_class(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, _ = _make_review_doc(acct)

    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"new_class": {"name": "Vendor Agreement", "description": "supplier deals"}},
    )
    assert res.status_code == 200
    card = res.json()
    slugs = {c["slug"] for c in card["classes"]}
    assert "vendor_agreement" in slugs
    with SessionLocal() as db:
        created = db.query(Class).filter_by(account_id=acct, slug="vendor_agreement").one()
        assert created.is_system is False


def test_assign_empty_400(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, _ = _make_review_doc(acct)
    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": []},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "no_classes"


def test_assign_unknown_class_404(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, _ = _make_review_doc(acct)
    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(uuid.uuid4())]},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "class_not_found"


def test_assign_foreign_document_404(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    doc_id, class_id = _make_review_doc(acct)
    # Same doc, but accessed under the company account → not found.
    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account, account="company_id"),
        json={"class_ids": [str(class_id)]},
    )
    assert res.status_code == 404


def test_assign_unknown_document_404(client, seeded_account) -> None:
    res = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(uuid.uuid4())]},
    )
    assert res.status_code == 404


def test_assign_add_mode_appends_and_keeps_primary(client, seeded_account) -> None:
    """mode='add' (drag-to-folder) appends a label without removing others; the
    existing primary stays primary and the added label is secondary."""
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        a = Class(account_id=acct, slug="invoice", name="Invoice", is_system=True)
        b = Class(account_id=acct, slug="report", name="Report", is_system=True)
        doc = Document(
            account_id=acct, source="web_upload", original_filename="d.pdf",
            file_hash=uuid.uuid4().hex, storage_path="/tmp/d.pdf", status="indexed",
        )
        db.add_all([a, b, doc])
        db.flush()
        db.add(DocumentClass(
            account_id=acct, document_id=doc.id, class_id=a.id,
            confidence=0.9, assigned_by="model", is_primary=True,
        ))
        db.commit()
        doc_id, b_id = doc.id, b.id

    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(b_id)], "mode": "add"},
    )
    assert res.status_code == 200

    with SessionLocal() as db:
        rows = db.query(DocumentClass).filter_by(document_id=doc_id).all()
        by_slug = {db.get(Class, r.class_id).slug: r for r in rows}
        assert set(by_slug) == {"invoice", "report"}  # existing kept + new added
        assert by_slug["invoice"].is_primary is True  # primary unchanged
        assert by_slug["report"].is_primary is False  # added as a secondary label


def test_assign_add_mode_on_unfiled_takes_primary(client, seeded_account) -> None:
    """Adding to a document with no classes makes the first added the primary."""
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        cls = Class(account_id=acct, slug="invoice", name="Invoice", is_system=True)
        doc = Document(
            account_id=acct, source="web_upload", original_filename="d.pdf",
            file_hash=uuid.uuid4().hex, storage_path="/tmp/d.pdf", status="indexed",
        )
        db.add_all([cls, doc])
        db.commit()
        doc_id, cls_id = doc.id, cls.id

    client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(cls_id)], "mode": "add"},
    )
    with SessionLocal() as db:
        row = db.query(DocumentClass).filter_by(document_id=doc_id).one()
        assert row.is_primary is True


def test_assign_set_primary_moves_primary_keeping_labels(client, seeded_account) -> None:
    """mode='set_primary' (drag-move) makes the dropped class primary while keeping
    the document's other labels; exactly one primary remains."""
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        a = Class(account_id=acct, slug="invoice", name="Invoice", is_system=True)
        b = Class(account_id=acct, slug="receipt", name="Receipt", is_system=True)
        target = Class(account_id=acct, slug="report", name="Report", is_system=True)
        doc = Document(
            account_id=acct, source="web_upload", original_filename="d.pdf",
            file_hash=uuid.uuid4().hex, storage_path="/tmp/d.pdf", status="indexed",
        )
        db.add_all([a, b, target, doc])
        db.flush()
        db.add_all([
            DocumentClass(account_id=acct, document_id=doc.id, class_id=a.id,
                          is_primary=True, assigned_by="model", confidence=0.9),
            DocumentClass(account_id=acct, document_id=doc.id, class_id=b.id,
                          is_primary=False, assigned_by="model", confidence=0.4),
        ])
        db.commit()
        doc_id, target_id = doc.id, target.id

    res = client.post(
        f"/api/v1/documents/{doc_id}/classes",
        headers=_headers(seeded_account),
        json={"class_ids": [str(target_id)], "mode": "set_primary"},
    )
    assert res.status_code == 200

    with SessionLocal() as db:
        rows = db.query(DocumentClass).filter_by(document_id=doc_id).all()
        by_slug = {db.get(Class, r.class_id).slug: r for r in rows}
        assert set(by_slug) == {"invoice", "receipt", "report"}  # labels kept + new
        assert by_slug["report"].is_primary is True   # dropped class is primary
        assert by_slug["invoice"].is_primary is False  # old primary demoted
        assert by_slug["receipt"].is_primary is False  # secondary stays secondary
        assert sum(1 for r in rows if r.is_primary) == 1
