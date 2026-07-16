"""Analytics endpoints — the usage and quality lenses (Phase 7).

Every number is derived **server-side** from the observability spine
(`documents`, `retrieval_traces`, `answer_ratings`, `processing_events`) so the
web and future native clients render identical figures without re-deriving
anything. All queries are account-scoped; time series are zero-filled by day so
charts never interpolate over missing dates.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, case, cast, func, select, text

from app.api.schemas import (
    AnalyticsQualityOut,
    AnalyticsUsageOut,
    MostAskedDocumentOut,
    SeriesPointOut,
    TopClassOut,
    UsageSeriesOut,
)
from app.core.scoping import AccountScope, get_current_account
from app.db.models import (
    AnswerRating,
    Class,
    Document,
    DocumentClass,
    ProcessingEvent,
    RetrievalTrace,
)

router = APIRouter(prefix="/api/v1", tags=["analytics"])

_RANGES = {"7d": 7, "30d": 30, "90d": 90}
_TOP_LIMIT = 8


def _parse_range(value: str) -> int:
    days = _RANGES.get(value)
    if days is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "bad_range", "message": "range must be one of 7d, 30d, 90d."},
        )
    return days


def _day_series(rows: list[tuple[dt.date, int]], start: dt.date, end: dt.date) -> list[dict]:
    """Zero-fill per-day counts across [start, end] (inclusive)."""
    by_day = dict(rows)
    series = []
    day = start
    while day <= end:
        series.append({"date": day, "count": by_day.get(day, 0)})
        day += dt.timedelta(days=1)
    return series


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(100.0 * numerator / denominator, 1)


@router.get("/analytics/usage", response_model=AnalyticsUsageOut)
def analytics_usage(
    range: str = Query(default="30d"),
    scope: AccountScope = Depends(get_current_account),
) -> AnalyticsUsageOut:
    """The usage lens: headline totals, per-day series, top folders, most-asked docs."""
    days = _parse_range(range)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    range_start_day = today - dt.timedelta(days=days - 1)
    range_start = dt.datetime.combine(range_start_day, dt.time.min, tzinfo=dt.timezone.utc)
    db = scope.db

    # Headlines: the archive (documents/storage) is a total; activity is in-range.
    doc_count, byte_sum = db.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.byte_size), 0)).where(
            Document.account_id == scope.account_id
        )
    ).one()
    queries, token_spend = db.execute(
        select(
            func.count(RetrievalTrace.id),
            func.coalesce(
                func.sum(
                    func.coalesce(RetrievalTrace.prompt_tokens, 0)
                    + func.coalesce(RetrievalTrace.completion_tokens, 0)
                ),
                0,
            ),
        ).where(
            RetrievalTrace.account_id == scope.account_id,
            RetrievalTrace.created_at >= range_start,
        )
    ).one()

    # Documents over time: per-day uploads in range, plus a cumulative running
    # total seeded with everything uploaded before the range (archive growth).
    # Day boundaries are UTC — plain date(timestamptz) uses the session
    # timezone and drifts from the UTC range around midnight.
    doc_day = func.date(func.timezone("UTC", Document.created_at))
    uploads_by_day = db.execute(
        select(doc_day, func.count(Document.id))
        .where(
            Document.account_id == scope.account_id,
            Document.created_at >= range_start,
        )
        .group_by(doc_day)
    ).all()
    before_range = db.scalar(
        select(func.count(Document.id)).where(
            Document.account_id == scope.account_id,
            Document.created_at < range_start,
        )
    )
    docs_series = _day_series(uploads_by_day, range_start_day, today)
    running = before_range or 0
    for point in docs_series:
        running += point["count"]
        point["cumulative"] = running

    trace_day = func.date(func.timezone("UTC", RetrievalTrace.created_at))
    queries_by_day = db.execute(
        select(trace_day, func.count(RetrievalTrace.id))
        .where(
            RetrievalTrace.account_id == scope.account_id,
            RetrievalTrace.created_at >= range_start,
        )
        .group_by(trace_day)
    ).all()

    # Top folders = primary classes (matches the archive's one-doc-one-folder view).
    top_classes = db.execute(
        select(Class.slug, Class.name, func.count(DocumentClass.document_id))
        .join(DocumentClass, DocumentClass.class_id == Class.id)
        .where(
            DocumentClass.account_id == scope.account_id,
            DocumentClass.is_primary.is_(True),
        )
        .group_by(Class.slug, Class.name)
        .order_by(func.count(DocumentClass.document_id).desc(), Class.slug)
        .limit(_TOP_LIMIT)
    ).all()

    # Most-asked documents: unnest citation jsonb; count each trace once per doc.
    most_asked = db.execute(
        text(
            """
            SELECT (c ->> 'document_id')::uuid AS document_id,
                   count(DISTINCT rt.id)       AS times
            FROM retrieval_traces rt
            CROSS JOIN LATERAL jsonb_array_elements(rt.citations) AS c
            WHERE rt.account_id = :account_id
              AND rt.created_at >= :range_start
              AND c ->> 'document_id' IS NOT NULL
            GROUP BY 1
            ORDER BY times DESC
            LIMIT :limit
            """
        ),
        {"account_id": scope.account_id, "range_start": range_start, "limit": _TOP_LIMIT},
    ).all()
    titles = {}
    if most_asked:
        titles = dict(
            db.execute(
                scope.select(Document)
                .with_only_columns(Document.id, func.coalesce(Document.title, Document.original_filename))
                .where(Document.id.in_([row.document_id for row in most_asked]))
            ).all()
        )

    return AnalyticsUsageOut(
        range_days=days,
        documents=doc_count,
        queries=queries,
        storage_bytes=int(byte_sum),
        token_spend=int(token_spend),
        series=UsageSeriesOut(
            documents_over_time=[SeriesPointOut(**p) for p in docs_series],
            queries_per_day=[SeriesPointOut(**p) for p in _day_series(queries_by_day, range_start_day, today)],
        ),
        top_classes=[TopClassOut(slug=s, name=n, count=c) for s, n, c in top_classes],
        most_asked_documents=[
            MostAskedDocumentOut(
                document_id=row.document_id,
                title=titles.get(row.document_id),
                count=row.times,
            )
            for row in most_asked
            if row.document_id in titles  # drop citations of since-deleted docs
        ],
    )


@router.get("/analytics/quality", response_model=AnalyticsQualityOut)
def analytics_quality(
    scope: AccountScope = Depends(get_current_account),
) -> AnalyticsQualityOut:
    """The quality lens: rating %, grounded %, retrieval latency, extraction success."""
    db = scope.db

    ratings_total, ratings_up = db.execute(
        select(
            func.count(AnswerRating.id),
            func.coalesce(func.sum(case((AnswerRating.rating == "up", 1), else_=0)), 0),
        ).where(AnswerRating.account_id == scope.account_id)
    ).one()

    supported_flag = RetrievalTrace.retrieval_plan["supported"].as_boolean()
    answers_total, answers_grounded, avg_latency = db.execute(
        select(
            func.count(RetrievalTrace.id),
            func.coalesce(func.sum(cast(supported_flag, Integer)), 0),
            func.avg(RetrievalTrace.latency_ms),
        ).where(RetrievalTrace.account_id == scope.account_id)
    ).one()

    extraction_ok, extraction_failed = db.execute(
        select(
            func.coalesce(func.sum(case((ProcessingEvent.status == "succeeded", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ProcessingEvent.status == "failed", 1), else_=0)), 0),
        ).where(
            ProcessingEvent.account_id == scope.account_id,
            ProcessingEvent.stage == "extraction",
        )
    ).one()

    return AnalyticsQualityOut(
        answer_rating_pct=_pct(ratings_up, ratings_total),
        grounded_pct=_pct(answers_grounded, answers_total),
        avg_retrieval_ms=int(avg_latency) if avg_latency is not None else None,
        extraction_success_pct=_pct(extraction_ok, extraction_ok + extraction_failed),
        ratings_count=ratings_total,
        answers_count=answers_total,
    )
