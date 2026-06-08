"""Unit tests for the aggregate stats + filtering added in audit IMP-BE-2 / IMP-BE-3."""

from __future__ import annotations

import pytest
from app.database import Base
from app.models import AnalysisLog
from app.repositories import AnalysisLogRepository
from app.validation.schemas import AnalysisPayload, AngleResult
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _add(db, **overrides):
    defaults = dict(
        media_type="image",
        runway_id="papi_24",
        global_state="correct_glidepath",
        original_filename="frame.jpg",
        confidence=0.9,
        angle_available=False,
        frame_count=1,
        processing_ms=100,
        result_json={},
    )
    defaults.update(overrides)
    db.add(AnalysisLog(**defaults))
    db.commit()


def test_stats_breakdowns_aggregate_whole_table(session):
    _add(session, runway_id="papi_24", global_state="correct_glidepath", media_type="image", confidence=0.9, processing_ms=100)
    _add(session, runway_id="papi_24", global_state="too_low", media_type="video", confidence=0.8, processing_ms=300)
    _add(session, runway_id="papi_06", global_state="correct_glidepath", media_type="image", confidence=0.7, processing_ms=200)

    stats = AnalysisLogRepository(session).stats()

    assert stats.total_analyses == 3
    assert stats.sample_size == 3
    assert stats.image_count == 2
    assert stats.video_count == 1
    assert stats.by_runway == {"papi_24": 2, "papi_06": 1}
    assert stats.by_global_state["correct_glidepath"] == 2
    assert stats.by_global_state["too_low"] == 1
    assert stats.by_media_type == {"image": 2, "video": 1}
    assert stats.avg_confidence == pytest.approx(0.8, abs=1e-6)
    assert stats.p50_processing_ms == 200  # nearest-rank of [100, 200, 300]


def test_stats_empty_table_is_zeroed(session):
    stats = AnalysisLogRepository(session).stats()
    assert stats.total_analyses == 0
    assert stats.image_count == 0
    assert stats.by_runway == {}
    assert stats.avg_confidence is None


def test_filters_and_count(session):
    _add(session, runway_id="papi_24", global_state="correct_glidepath", confidence=0.9)
    _add(session, runway_id="papi_06", global_state="too_low", confidence=0.5)
    repo = AnalysisLogRepository(session)

    assert repo.count() == 2
    assert repo.count(runway_id="papi_24") == 1
    assert repo.count(global_state="too_low") == 1
    assert repo.count(min_confidence=0.8) == 1

    rows = repo.list_recent(50, 0, runway_id="papi_06")
    assert [r.runway_id for r in rows] == ["papi_06"]


def test_iter_filtered_for_csv_export(session):
    _add(session, runway_id="papi_24")
    _add(session, runway_id="papi_06")
    repo = AnalysisLogRepository(session)

    assert len(repo.iter_filtered()) == 2
    assert len(repo.iter_filtered(runway_id="papi_24")) == 1


def test_create_from_payload_truncates_overlong_drone_id(session):
    """An unbounded client drone_id is capped to the VARCHAR(128) column width so the
    Postgres write can't raise StringDataRightTruncation (503) and orphan the artifact
    (SQLite ignores column width, so the cap is what protects production) — audit."""
    payload = AnalysisPayload(
        media_type="image",
        original_filename="frame.jpg",
        runway_id="papi_24",
        drone_id="x" * 300,
        global_state="unknown",
        lamps=[],
        confidence=0.5,
        frame_count=1,
        processing_ms=1,
        angle=AngleResult(angle_available=False, angle_note="no metadata"),
    )
    log = AnalysisLogRepository(session).create_from_payload(payload)
    assert log.drone_id == "x" * 128


def test_create_from_payload_deletes_artifact_when_commit_fails(session, tmp_path, monkeypatch):
    """The annotated artifact is written by inference BEFORE the log commit. If the commit
    fails (DB error, column-width truncation), the artifact must be deleted rather than
    orphaning on disk with no log pointing to it (audit P3)."""
    from types import SimpleNamespace

    from app.repositories import analysis_logs as repo_module

    monkeypatch.setattr(repo_module, "get_settings", lambda: SimpleNamespace(exports_dir=tmp_path))
    artifact = tmp_path / "abc_annotated.mp4"
    artifact.write_bytes(b"fake artifact bytes")

    payload = AnalysisPayload(
        media_type="video",
        original_filename="clip.mp4",
        runway_id="papi_24",
        global_state="unknown",
        lamps=[],
        confidence=0.5,
        frame_count=1,
        processing_ms=1,
        angle=AngleResult(angle_available=False, angle_note="no metadata"),
        artifact_url="/media/abc_annotated.mp4",
    )

    def _boom():
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(session, "commit", _boom)

    with pytest.raises(RuntimeError):
        AnalysisLogRepository(session).create_from_payload(payload)

    assert not artifact.exists()  # orphan cleaned up on the failed persist
