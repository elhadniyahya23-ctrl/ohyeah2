from worker.names_source import resolve_names


def test_resolve_names_from_job_only():
    job = {"names": ["a", "b", "c"]}
    assert resolve_names(job, "") == ["a", "b", "c"]
