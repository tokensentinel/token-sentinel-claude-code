"""Live health probe."""

from __future__ import annotations

from tokensentinel_claude_code.health import probe_health


def test_probe_health_imports(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.setenv("TOKENSENTINEL_MODE", "observe")
    report = probe_health()
    assert report.plugin_version
    assert report.sdk_version is not None
    assert report.adapter_version is not None
    assert report.sessions_db_ok is True
    assert report.status in {"healthy", "degraded", "down"}
    assert any("sqlite_rehydrate" in n for n in report.notes)
