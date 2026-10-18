from services.plans import ADMIN_OWNER_TOKENS, ADMIN_USERNAMES, is_admin, is_admin_token, is_admin_username


def test_admin_usernames_allowlist():
    assert "asiopitos" in ADMIN_USERNAMES
    assert "eya" in ADMIN_USERNAMES
    assert is_admin_username("ASIOPITOS")
    assert is_admin_username("eya")
    assert not is_admin_username("randomuser")


def test_admin_owner_tokens_allowlist():
    from types import SimpleNamespace

    assert "b0d641aa07c0457f81c231cb7dda49ee" in ADMIN_OWNER_TOKENS
    assert "20bd3b72-ecd1-46da-986f-15573bcbe8c7" in ADMIN_OWNER_TOKENS
    assert is_admin_token("b0d641aa07c0457f81c231cb7dda49ee")
    assert is_admin_token("20bd3b72-ecd1-46da-986f-15573bcbe8c7")
    assert not is_admin_token("not-an-owner")
    owner = SimpleNamespace(username="someone", token="b0d641aa07c0457f81c231cb7dda49ee")
    assert is_admin(owner) is True
    other = SimpleNamespace(username="someone", token="nope")
    assert is_admin(other) is False


def test_grantable_plans_keys():
    from routers.admin import GRANTABLE_PLANS

    assert "premium-1-week" in GRANTABLE_PLANS
    assert "premium-1-month" in GRANTABLE_PLANS
    assert "premium-lifetime" in GRANTABLE_PLANS
    assert "premium-custom" in GRANTABLE_PLANS
    assert GRANTABLE_PLANS["premium-lifetime"]["duration_days"] is None
    assert GRANTABLE_PLANS["premium-custom"]["rank"] == "Premium"


def test_audit_row_shape():
    from types import SimpleNamespace

    from services.admin_audit import audit_row

    row = SimpleNamespace(
        id=1,
        actor_id=2,
        actor_username="eya",
        action="grant_plan",
        target_user_id=9,
        target_username="client",
        detail="Granted 7-Day Premium",
        meta={"plan_id": "premium-1-week"},
        actor_ip="1.2.3.4",
        created_at=None,
    )
    payload = audit_row(row)
    assert payload["actor_username"] == "eya"
    assert payload["action"] == "grant_plan"
    assert payload["meta"]["plan_id"] == "premium-1-week"
    assert payload["created_at"] is None

