"""Class-catalog endpoints: list (with counts), create custom, delete, isolation."""

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


def test_list_classes_empty_and_auth(client, seeded_account) -> None:
    assert client.get("/api/v1/classes").status_code == 401
    res = client.get("/api/v1/classes", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert res.json() == []  # seeded_account seeds no classes


def test_create_class_derives_slug(client, seeded_account) -> None:
    res = client.post(
        "/api/v1/classes", headers=_headers(seeded_account),
        json={"name": "Purchase Order", "description": "POs issued to suppliers"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["slug"] == "purchase_order"
    assert body["is_system"] is False
    assert body["document_count"] == 0
    # and it now shows up in the list
    listed = client.get("/api/v1/classes", headers=_headers(seeded_account)).json()
    assert [c["slug"] for c in listed] == ["purchase_order"]


def test_create_duplicate_slug_conflict(client, seeded_account) -> None:
    h = _headers(seeded_account)
    client.post("/api/v1/classes", headers=h, json={"name": "Meeting Notes"})
    res = client.post("/api/v1/classes", headers=h, json={"name": "meeting  notes"})  # same slug
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "class_exists"


def test_create_invalid_name_400(client, seeded_account) -> None:
    res = client.post("/api/v1/classes", headers=_headers(seeded_account), json={"name": "!!!"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "invalid_name"


def test_delete_custom_class(client, seeded_account) -> None:
    h = _headers(seeded_account)
    cid = client.post("/api/v1/classes", headers=h, json={"name": "Temp"}).json()["id"]
    assert client.delete(f"/api/v1/classes/{cid}", headers=h).status_code == 204
    assert client.get("/api/v1/classes", headers=h).json() == []


def test_delete_system_class_immutable(client, seeded_account) -> None:
    with SessionLocal() as db:
        sys_cls = Class(
            account_id=seeded_account["personal_id"], slug="invoice",
            name="Invoice", is_system=True,
        )
        db.add(sys_cls)
        db.commit()
        cid = sys_cls.id
    res = client.delete(f"/api/v1/classes/{cid}", headers=_headers(seeded_account))
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "system_immutable"


def test_delete_unknown_class_404(client, seeded_account) -> None:
    res = client.delete(f"/api/v1/classes/{uuid.uuid4()}", headers=_headers(seeded_account))
    assert res.status_code == 404


def test_class_account_isolation(client, seeded_account) -> None:
    # Created under personal...
    cid = client.post(
        "/api/v1/classes", headers=_headers(seeded_account), json={"name": "Secret"}
    ).json()["id"]
    # ...invisible and undeletable from the company account.
    assert client.get("/api/v1/classes", headers=_headers(seeded_account, account="company_id")).json() == []
    res = client.delete(
        f"/api/v1/classes/{cid}", headers=_headers(seeded_account, account="company_id")
    )
    assert res.status_code == 404


def test_list_reports_document_count(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        cls = Class(account_id=acct, slug="report", name="Report", is_system=False)
        doc = Document(
            account_id=acct, source="web_upload", original_filename="r.pdf",
            file_hash=uuid.uuid4().hex, storage_path="/tmp/r.pdf", status="indexed",
        )
        db.add_all([cls, doc])
        db.flush()
        db.add(DocumentClass(
            account_id=acct, document_id=doc.id, class_id=cls.id,
            confidence=0.9, is_primary=True,
        ))
        db.commit()
    listed = client.get("/api/v1/classes", headers=_headers(seeded_account)).json()
    report = next(c for c in listed if c["slug"] == "report")
    assert report["document_count"] == 1


def test_document_count_and_primary_filter_ignore_secondary_labels(client, seeded_account) -> None:
    """A document counts under, and lists in, only its PRIMARY class' folder."""
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        inv = Class(account_id=acct, slug="invoice", name="Invoice", is_system=True)
        rpt = Class(account_id=acct, slug="report", name="Report", is_system=True)
        doc = Document(account_id=acct, source="web_upload", original_filename="i.pdf",
                       file_hash=uuid.uuid4().hex, storage_path="/tmp/i.pdf", status="indexed")
        db.add_all([inv, rpt, doc])
        db.flush()
        db.add_all([
            DocumentClass(account_id=acct, document_id=doc.id, class_id=inv.id,
                          confidence=0.9, is_primary=True),
            DocumentClass(account_id=acct, document_id=doc.id, class_id=rpt.id,
                          confidence=0.4, is_primary=False),  # secondary label
        ])
        db.commit()
        doc_id = str(doc.id)

    h = _headers(seeded_account)
    listed = client.get("/api/v1/classes", headers=h).json()
    assert next(c for c in listed if c["slug"] == "invoice")["document_count"] == 1
    assert next(c for c in listed if c["slug"] == "report")["document_count"] == 0

    # Primary browse: the doc appears under invoice, not under report.
    inv_primary = client.get("/api/v1/documents?class=invoice&primary=true", headers=h).json()
    assert [d["id"] for d in inv_primary["items"]] == [doc_id]
    rpt_primary = client.get("/api/v1/documents?class=report&primary=true", headers=h).json()
    assert rpt_primary["items"] == []

    # Default (any-label) filter still sees the secondary label — recall path.
    rpt_any = client.get("/api/v1/documents?class=report", headers=h).json()
    assert [d["id"] for d in rpt_any["items"]] == [doc_id]


def test_create_class_with_parent(client, seeded_account) -> None:
    h = _headers(seeded_account)
    parent_id = client.post("/api/v1/classes", headers=h, json={"name": "Financial"}).json()["id"]
    res = client.post(
        "/api/v1/classes", headers=h,
        json={"name": "Invoice", "parent_id": parent_id},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["parent_id"] == parent_id
    assert body["parent_slug"] == "financial"
    # the parent link surfaces in the list too
    listed = client.get("/api/v1/classes", headers=h).json()
    inv = next(c for c in listed if c["slug"] == "invoice")
    assert inv["parent_slug"] == "financial"


def test_create_class_bad_parent_400(client, seeded_account) -> None:
    res = client.post(
        "/api/v1/classes", headers=_headers(seeded_account),
        json={"name": "Orphan", "parent_id": str(uuid.uuid4())},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "bad_parent"


def test_documents_filter_by_parent_class_includes_children(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        fin = Class(account_id=acct, slug="financial", name="Financial", is_system=True)
        db.add(fin)
        db.flush()
        inv = Class(account_id=acct, slug="invoice", name="Invoice", parent_id=fin.id, is_system=True)
        db.add(inv)
        doc = Document(account_id=acct, source="web_upload", original_filename="i.pdf",
                       file_hash=uuid.uuid4().hex, storage_path="/tmp/i.pdf", status="indexed")
        db.add(doc)
        db.flush()
        db.add(DocumentClass(account_id=acct, document_id=doc.id, class_id=inv.id, confidence=0.9))
        db.commit()
        doc_id = str(doc.id)

    # Filtering by the PARENT slug returns the child-labelled document.
    res = client.get("/api/v1/documents?class=financial", headers=_headers(seeded_account))
    assert res.status_code == 200
    assert [d["id"] for d in res.json()["items"]] == [doc_id]


def test_documents_filter_by_class(client, seeded_account) -> None:
    acct = seeded_account["personal_id"]
    with SessionLocal() as db:
        inv = Class(account_id=acct, slug="invoice", name="Invoice", is_system=True)
        rpt = Class(account_id=acct, slug="report", name="Report", is_system=True)
        d_inv = Document(account_id=acct, source="web_upload", original_filename="i.pdf",
                         file_hash=uuid.uuid4().hex, storage_path="/tmp/i.pdf", status="indexed")
        d_rpt = Document(account_id=acct, source="web_upload", original_filename="r.pdf",
                         file_hash=uuid.uuid4().hex, storage_path="/tmp/r.pdf", status="indexed")
        db.add_all([inv, rpt, d_inv, d_rpt])
        db.flush()
        db.add_all([
            DocumentClass(account_id=acct, document_id=d_inv.id, class_id=inv.id, confidence=0.9),
            DocumentClass(account_id=acct, document_id=d_rpt.id, class_id=rpt.id, confidence=0.9),
        ])
        db.commit()
        inv_id = str(d_inv.id)

    res = client.get("/api/v1/documents?class=invoice", headers=_headers(seeded_account))
    assert res.status_code == 200
    items = res.json()["items"]
    assert [d["id"] for d in items] == [inv_id]  # only the invoice doc, not the report


def test_rename_custom_class(client, seeded_account) -> None:
    h = _headers(seeded_account)
    created = client.post("/api/v1/classes", headers=h, json={"name": "Draffts"}).json()
    res = client.patch(f"/api/v1/classes/{created['id']}", headers=h, json={"name": "Drafts"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Drafts"
    assert body["slug"] == created["slug"]  # slug stays stable


def test_rename_system_class_409(client, seeded_account) -> None:
    with SessionLocal() as db:
        sys_cls = Class(
            account_id=seeded_account["personal_id"], slug="invoice",
            name="Invoice", is_system=True,
        )
        db.add(sys_cls)
        db.commit()
        cid = sys_cls.id
    res = client.patch(f"/api/v1/classes/{cid}", headers=_headers(seeded_account), json={"name": "Nope"})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "system_immutable"


def test_rename_unknown_class_404(client, seeded_account) -> None:
    res = client.patch(
        f"/api/v1/classes/{uuid.uuid4()}", headers=_headers(seeded_account), json={"name": "X"}
    )
    assert res.status_code == 404
