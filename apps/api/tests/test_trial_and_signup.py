from services.trial_billing import billable_trial_seconds, session_elapsed


def test_normalize_ip_strips_mapped():
    from services.signup_guard import normalize_ip

    assert normalize_ip("::ffff:1.2.3.4") == "1.2.3.4"
    assert normalize_ip(" 8.8.8.8 ") == "8.8.8.8"


def test_session_elapsed_running():
    import time

    started = time.time() - 12
    data = {
        "started_at": started,
        "running_started_at": started,
        "elapsed_seconds": 3,
        "state": "running",
        "checks_done": 1,
    }
    elapsed = session_elapsed(data)
    assert elapsed >= 11


def test_session_elapsed_queued_does_not_tick():
    import time

    started = time.time() - 120
    data = {"started_at": started, "elapsed_seconds": 0, "state": "queued"}
    assert session_elapsed(data) == 0


def test_session_elapsed_stopped_uses_stored():
    data = {"started_at": 1, "elapsed_seconds": 42, "state": "stopped"}
    assert session_elapsed(data) == 42


def test_billable_zero_activity_does_not_burn_trial():
    import time

    started = time.time() - 200
    data = {
        "started_at": started,
        "running_started_at": started,
        "elapsed_seconds": 0,
        "state": "running",
        "checks_done": 0,
        "rate_limits": 0,
        "proxy_misses": 0,
        "errors": 0,
    }
    assert billable_trial_seconds(data) == 0


def test_billable_queued_is_zero_even_if_mislabelled_fields():
    import time

    started = time.time() - 200
    data = {
        "started_at": started,
        "elapsed_seconds": 0,
        "state": "queued",
        "checks_done": 10,
    }
    assert billable_trial_seconds(data) == 0


def test_billable_counts_when_checks_running():
    import time

    started = time.time() - 30
    data = {
        "started_at": started,
        "running_started_at": started,
        "elapsed_seconds": 0,
        "state": "running",
        "checks_done": 500,
    }
    assert billable_trial_seconds(data) >= 29


def test_billable_counts_late_proxy_as_activity():
    import time

    started = time.time() - 20
    data = {
        "started_at": started - 100,
        "running_started_at": started,
        "elapsed_seconds": 0,
        "state": "running",
        "checks_done": 0,
        "proxy_misses": 5,
    }
    assert billable_trial_seconds(data) >= 18


def test_session_elapsed_running_ignores_queue_wait():
    import time

    queued_at = time.time() - 200
    running_at = time.time() - 10
    data = {
        "started_at": queued_at,
        "running_started_at": running_at,
        "elapsed_seconds": 0,
        "state": "running",
        "checks_done": 1,
    }
    elapsed = session_elapsed(data)
    assert elapsed < 30
    assert elapsed >= 8


def test_session_elapsed_without_running_anchor_and_no_activity_is_zero():
    import time

    data = {
        "started_at": time.time() - 200,
        "elapsed_seconds": 0,
        "state": "running",
        "checks_done": 0,
    }
    assert session_elapsed(data) == 0
