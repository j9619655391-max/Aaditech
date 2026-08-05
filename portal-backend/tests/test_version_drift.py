"""Unit tests for version_drift. Run with: pytest tests/test_version_drift.py
(also runnable standalone with unittest — see bottom — since this module
has zero external dependencies, unlike the other integration client tests.)"""
from app.integrations.version_drift import check_version_drift, summarize_drift


def test_agent_within_threshold_not_stale():
    agents = [{"id": "001", "name": "srv01", "version": "v4.8.0"}]
    results = check_version_drift(agents, expected_version="v4.9.0", threshold=2)

    assert results[0].minor_versions_behind == 1
    assert results[0].is_stale is False


def test_agent_beyond_threshold_is_stale():
    agents = [{"id": "002", "name": "srv02", "version": "v4.5.0"}]
    results = check_version_drift(agents, expected_version="v4.9.0", threshold=2)

    assert results[0].minor_versions_behind == 4
    assert results[0].is_stale is True


def test_major_version_mismatch_always_stale():
    agents = [{"id": "003", "name": "srv03", "version": "v3.9.0"}]
    results = check_version_drift(agents, expected_version="v4.9.0", threshold=2)

    assert results[0].is_stale is True


def test_unparseable_version_defaults_safely():
    agents = [{"id": "004", "name": "srv04", "version": "unknown"}]
    results = check_version_drift(agents, expected_version="v4.9.0", threshold=2)

    # (0,0) vs (4,9) -> major mismatch -> stale, and doesn't crash
    assert results[0].is_stale is True


def test_summarize_drift_counts_correctly():
    agents = [
        {"id": "1", "name": "a", "version": "v4.9.0"},   # current, not stale
        {"id": "2", "name": "b", "version": "v4.5.0"},   # stale
        {"id": "3", "name": "c", "version": "v4.8.0"},   # not stale (1 behind, threshold 2)
    ]
    results = check_version_drift(agents, expected_version="v4.9.0", threshold=2)
    summary = summarize_drift(results)

    assert summary["total_agents"] == 3
    assert summary["stale_agents"] == 1
    assert summary["stale_agent_names"] == ["b"]


if __name__ == "__main__":
    # Allows direct execution without pytest installed: python3 tests/test_version_drift.py
    import sys
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
