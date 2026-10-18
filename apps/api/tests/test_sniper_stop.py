from services.sniper_queue import stop_flag_key


def test_stop_flag_key():
    assert stop_flag_key("tok", "discord") == "sniper:stop:tok:discord"


def test_request_sniper_stop_helpers_importable():
    from services import sniper_queue

    assert callable(sniper_queue.set_stop_flag)
    assert callable(sniper_queue.clear_stop_flag)
    assert callable(sniper_queue.is_stop_requested)
    assert callable(sniper_queue.purge_queued_jobs)
    assert callable(sniper_queue.request_sniper_stop)
