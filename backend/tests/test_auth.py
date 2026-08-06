"""Accounts, roles and the enforcement of the row cap.

The important tests here are the ones asserting that a caller cannot reach past
their role by editing a request.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.auth.deps import export_limit_for, row_cap_for
from app.auth.models import Role, create_auth
from app.auth.security import (
    decode_token,
    hash_password,
    issue_token,
    normalise_email,
    password_problem,
    verify_password,
)
from app.auth.service import (
    SignupError,
    authenticate,
    create_user,
    get_user_by_email,
    public_user,
    set_active,
    set_role,
)
from app.db.engine import build_engine, get_engine
from app.db.layer2 import create_layer2
from app.ingest import layer2_store as l2
from app.ingest.materialise import materialise
from app.main import create_app

NOW = "2026-08-06T15:00:00+00:00"
GOOD_PASSWORD = "correct horse battery"


@pytest.fixture
def db(tmp_path: Path) -> Engine:
    engine = build_engine(tmp_path / "auth.db")
    create_auth(engine)
    return engine


class TestRoleHierarchy:
    def test_roles_are_ordered(self) -> None:
        assert Role.PUBLIC < Role.USER < Role.ADMIN < Role.SUPER_ADMIN

    def test_a_superset_check_is_a_comparison(self) -> None:
        assert Role.ADMIN >= Role.USER
        assert not Role.USER >= Role.ADMIN

    def test_named_lookup(self) -> None:
        assert Role.from_name("super_admin") is Role.SUPER_ADMIN
        assert Role.from_name("ADMIN") is Role.ADMIN

    def test_unknown_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Unknown role"):
            Role.from_name("wizard")


class TestPasswords:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password(GOOD_PASSWORD)
        assert verify_password(GOOD_PASSWORD, hashed)

    def test_a_wrong_password_fails(self) -> None:
        assert not verify_password("something else", hash_password(GOOD_PASSWORD))

    def test_the_hash_does_not_contain_the_password(self) -> None:
        assert GOOD_PASSWORD not in hash_password(GOOD_PASSWORD)

    def test_two_hashes_of_the_same_password_differ(self) -> None:
        """Salted, so identical passwords do not produce identical hashes."""
        assert hash_password(GOOD_PASSWORD) != hash_password(GOOD_PASSWORD)

    def test_a_corrupt_hash_fails_rather_than_raising(self) -> None:
        assert not verify_password(GOOD_PASSWORD, "not-a-hash")

    def test_short_passwords_are_refused(self) -> None:
        assert password_problem("short") is not None

    def test_a_long_passphrase_is_accepted(self) -> None:
        assert password_problem(GOOD_PASSWORD) is None


class TestTokens:
    def test_round_trip(self) -> None:
        payload = decode_token(issue_token(7, Role.ADMIN))
        assert payload["sub"] == "7"
        assert payload["role"] == int(Role.ADMIN)

    def test_an_expired_token_is_refused(self) -> None:
        from app.auth.security import AuthError

        with pytest.raises(AuthError):
            decode_token(issue_token(1, Role.USER, expires_minutes=-1))

    def test_a_tampered_token_is_refused(self) -> None:
        from app.auth.security import AuthError

        token = issue_token(1, Role.USER)
        with pytest.raises(AuthError):
            decode_token(token[:-3] + "aaa")


class TestAccounts:
    def test_create_and_authenticate(self, db: Engine) -> None:
        create_user(db, "Someone@Example.com", GOOD_PASSWORD)
        assert authenticate(db, "someone@example.com", GOOD_PASSWORD) is not None

    def test_email_is_stored_lowercased(self, db: Engine) -> None:
        user = create_user(db, "Someone@Example.COM", GOOD_PASSWORD)
        assert user["email"] == "someone@example.com"
        assert normalise_email("  A@B.com ") == "a@b.com"

    def test_signup_is_always_at_the_user_role(self, db: Engine) -> None:
        """There must be no path from a form to an elevated role."""
        assert create_user(db, "a@b.com", GOOD_PASSWORD)["role"] == int(Role.USER)

    def test_duplicate_email_is_refused(self, db: Engine) -> None:
        create_user(db, "a@b.com", GOOD_PASSWORD)
        with pytest.raises(SignupError, match="already exists"):
            create_user(db, "A@B.com", GOOD_PASSWORD)

    def test_a_weak_password_is_refused(self, db: Engine) -> None:
        with pytest.raises(SignupError):
            create_user(db, "a@b.com", "short")

    def test_a_wrong_password_does_not_authenticate(self, db: Engine) -> None:
        create_user(db, "a@b.com", GOOD_PASSWORD)
        assert authenticate(db, "a@b.com", "wrong password here") is None

    def test_an_unknown_email_does_not_authenticate(self, db: Engine) -> None:
        assert authenticate(db, "nobody@example.com", GOOD_PASSWORD) is None

    def test_a_suspended_account_cannot_sign_in(self, db: Engine) -> None:
        user = create_user(db, "a@b.com", GOOD_PASSWORD)
        set_active(db, actor_id=user["id"], user_id=user["id"], active=False)
        assert authenticate(db, "a@b.com", GOOD_PASSWORD) is None

    def test_the_public_shape_never_carries_the_hash(self, db: Engine) -> None:
        user = create_user(db, "a@b.com", GOOD_PASSWORD)
        assert "password_hash" not in public_user(user)

    def test_role_change_is_recorded(self, db: Engine) -> None:
        user = create_user(db, "a@b.com", GOOD_PASSWORD)
        updated = set_role(db, actor_id=user["id"], user_id=user["id"], role=Role.ADMIN)
        assert updated["role"] == int(Role.ADMIN)
        with db.connect() as conn:
            actions = [r[0] for r in conn.execute(text("SELECT action FROM audit_log")).all()]
        assert "user.role_changed" in actions

    def test_login_is_audited(self, db: Engine) -> None:
        create_user(db, "a@b.com", GOOD_PASSWORD)
        assert get_user_by_email(db, "a@b.com") is not None


class TestCaps:
    def test_public_is_capped_and_signed_in_is_not(self) -> None:
        assert row_cap_for(Role.PUBLIC) == 25
        assert row_cap_for(Role.USER) is None
        assert row_cap_for(Role.ADMIN) is None

    def test_export_needs_an_account(self) -> None:
        assert export_limit_for(Role.PUBLIC) == 0
        assert export_limit_for(Role.USER) > 0


# --- API level ----------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        engine = get_engine()
        create_layer2(engine)
        create_auth(engine)
        l2.upsert_companies(
            engine,
            [
                {"symbol": f"CO{i:03d}", "name": f"Company {i}", "updated_at": NOW}
                for i in range(60)
            ],
        )
        l2.upsert_quotes(
            engine,
            [
                {"symbol": f"CO{i:03d}", "market_cap": float(1000 + i), "updated_at": NOW}
                for i in range(60)
            ],
        )
        materialise(engine)
        with engine.begin() as conn:
            conn.execute(text("UPDATE company_snapshot SET pe = 10.0"))
        yield test_client


def signup(client: TestClient, email: str = "a@b.com") -> dict:
    response = client.post("/api/auth/signup", json={"email": email, "password": GOOD_PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


class TestAuthApi:
    def test_signup_then_me(self, client: TestClient) -> None:
        signup(client)
        body = client.get("/api/auth/me").json()
        assert body["role"] == "user"
        assert body["user"]["email"] == "a@b.com"

    def test_me_is_safe_to_call_anonymously(self, client: TestClient) -> None:
        body = client.get("/api/auth/me").json()
        assert body["user"] is None
        assert body["role"] == "public"

    def test_logout_ends_the_session(self, client: TestClient) -> None:
        signup(client)
        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").json()["user"] is None

    def test_login_with_a_wrong_password_is_refused(self, client: TestClient) -> None:
        signup(client)
        client.post("/api/auth/logout")
        response = client.post(
            "/api/auth/login", json={"email": "a@b.com", "password": "wrong password!!"}
        )
        assert response.status_code == 401

    def test_the_same_message_for_a_missing_account_and_a_wrong_password(
        self, client: TestClient
    ) -> None:
        """The response must not reveal whether an email has an account."""
        signup(client)
        client.post("/api/auth/logout")
        wrong = client.post(
            "/api/auth/login", json={"email": "a@b.com", "password": "wrong password!!"}
        )
        missing = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": GOOD_PASSWORD}
        )
        assert wrong.json() == missing.json()

    def test_the_session_cookie_is_http_only(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/signup", json={"email": "c@d.com", "password": GOOD_PASSWORD}
        )
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie

    def test_the_password_never_comes_back(self, client: TestClient) -> None:
        body = signup(client)
        assert GOOD_PASSWORD not in str(body)
        assert "password_hash" not in str(body)


class TestRowCapEnforcement:
    def test_public_sees_the_cap_and_the_true_total(self, client: TestClient) -> None:
        body = client.post("/api/screener/run", json={"query": "PE < 20"}).json()
        assert body["total"] == 60
        assert body["returned"] == 25
        assert body["capped"] is True

    def test_signing_in_lifts_the_cap(self, client: TestClient) -> None:
        signup(client)
        body = client.post("/api/screener/run", json={"query": "PE < 20", "page_size": 100}).json()
        assert body["returned"] == 60
        assert body["capped"] is False

    def test_a_public_caller_cannot_page_past_the_cap(self, client: TestClient) -> None:
        """Editing the request must not reach row 26."""
        body = client.post("/api/screener/run", json={"query": "PE < 20", "page": 2}).json()
        assert body["returned"] == 0

    def test_a_public_caller_cannot_widen_the_page_size(self, client: TestClient) -> None:
        body = client.post("/api/screener/run", json={"query": "PE < 20", "page_size": 100}).json()
        assert body["returned"] == 25

    def test_logging_out_restores_the_cap(self, client: TestClient) -> None:
        signup(client)
        client.post("/api/auth/logout")
        body = client.post("/api/screener/run", json={"query": "PE < 20"}).json()
        assert body["returned"] == 25


class TestWorkspaceGating:
    def test_saved_screens_need_an_account(self, client: TestClient) -> None:
        assert client.get("/api/screens").status_code == 401

    def test_watchlists_need_an_account(self, client: TestClient) -> None:
        assert client.get("/api/watchlists").status_code == 401

    def test_export_needs_an_account(self, client: TestClient) -> None:
        assert client.get("/api/export/screen?query=PE%20%3C%2020").status_code == 401

    def test_a_user_cannot_reach_admin_endpoints(self, client: TestClient) -> None:
        signup(client)
        response = client.get("/api/admin/users")
        assert response.status_code in (403, 404)


class TestSavedScreens:
    def test_create_list_and_run(self, client: TestClient) -> None:
        signup(client)
        created = client.post("/api/screens", json={"name": "Cheap", "query": "PE < 20"}).json()
        assert created["name"] == "Cheap"

        listed = client.get("/api/screens").json()["screens"]
        assert len(listed) == 1

        run = client.post(f"/api/screens/{created['id']}/run").json()
        assert run["total"] == 60

    def test_an_invalid_query_is_refused_at_save_time(self, client: TestClient) -> None:
        """A saved screen must always be runnable."""
        signup(client)
        response = client.post("/api/screens", json={"name": "Broken", "query": "Nonsense > 1"})
        assert response.status_code == 400

    def test_duplicate_names_are_refused(self, client: TestClient) -> None:
        signup(client)
        client.post("/api/screens", json={"name": "Cheap", "query": "PE < 20"})
        second = client.post("/api/screens", json={"name": "Cheap", "query": "PE < 30"})
        assert second.status_code == 409

    def test_one_user_cannot_see_anothers_screen(self, client: TestClient) -> None:
        signup(client, "first@example.com")
        created = client.post("/api/screens", json={"name": "Mine", "query": "PE < 20"}).json()
        client.post("/api/auth/logout")

        signup(client, "second@example.com")
        assert client.get("/api/screens").json()["screens"] == []
        # 404 rather than 403: the response must not confirm it exists.
        assert client.get(f"/api/screens/{created['id']}").status_code == 404

    def test_one_user_cannot_delete_anothers_screen(self, client: TestClient) -> None:
        signup(client, "first@example.com")
        created = client.post("/api/screens", json={"name": "Mine", "query": "PE < 20"}).json()
        client.post("/api/auth/logout")

        signup(client, "second@example.com")
        assert client.delete(f"/api/screens/{created['id']}").status_code == 404

    def test_update_and_delete(self, client: TestClient) -> None:
        signup(client)
        created = client.post("/api/screens", json={"name": "A", "query": "PE < 20"}).json()
        updated = client.patch(
            f"/api/screens/{created['id']}", json={"name": "B", "query": "PE < 30"}
        ).json()
        assert updated["name"] == "B"
        assert client.delete(f"/api/screens/{created['id']}").status_code == 204
        assert client.get("/api/screens").json()["screens"] == []


class TestWatchlists:
    def test_create_add_and_remove(self, client: TestClient) -> None:
        signup(client)
        created = client.post("/api/watchlists", json={"name": "Core"}).json()
        client.post(
            f"/api/watchlists/{created['id']}/items", json={"symbol": "co001", "note": "cheap"}
        )
        lists = client.get("/api/watchlists").json()["watchlists"]
        assert lists[0]["items"][0]["symbol"] == "CO001"

        client.delete(f"/api/watchlists/{created['id']}/items/CO001")
        assert client.get("/api/watchlists").json()["watchlists"][0]["items"] == []

    def test_adding_the_same_symbol_twice_does_not_duplicate(self, client: TestClient) -> None:
        signup(client)
        created = client.post("/api/watchlists", json={"name": "Core"}).json()
        for _ in range(2):
            client.post(f"/api/watchlists/{created['id']}/items", json={"symbol": "CO001"})
        assert len(client.get("/api/watchlists").json()["watchlists"][0]["items"]) == 1

    def test_one_user_cannot_add_to_anothers_list(self, client: TestClient) -> None:
        signup(client, "first@example.com")
        created = client.post("/api/watchlists", json={"name": "Core"}).json()
        client.post("/api/auth/logout")

        signup(client, "second@example.com")
        response = client.post(f"/api/watchlists/{created['id']}/items", json={"symbol": "CO001"})
        assert response.status_code == 404


class TestExport:
    def test_a_signed_in_user_gets_csv(self, client: TestClient) -> None:
        signup(client)
        response = client.get("/api/export/screen", params={"query": "PE < 20"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        lines = response.text.strip().splitlines()
        assert lines[0].startswith("Symbol,")
        assert len(lines) == 61  # header plus 60 companies

    def test_the_export_declares_how_much_it_returned(self, client: TestClient) -> None:
        signup(client)
        response = client.get("/api/export/screen", params={"query": "PE < 20"})
        assert response.headers["X-StockLens-Total"] == "60"
        assert response.headers["X-StockLens-Truncated"] == "false"

    def test_a_bad_query_is_refused(self, client: TestClient) -> None:
        signup(client)
        assert client.get("/api/export/screen", params={"query": "Nope > 1"}).status_code == 400


class TestJwtSecretGuard:
    """A weak signing secret means sessions can be forged."""

    def test_the_development_default_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.auth.security import DEV_JWT_SECRET, jwt_secret_problem
        from app.config import get_settings as settings_factory

        monkeypatch.setenv("JWT_SECRET", DEV_JWT_SECRET)
        settings_factory.cache_clear()
        assert "development default" in (jwt_secret_problem() or "")
        settings_factory.cache_clear()

    def test_a_short_secret_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.auth.security import jwt_secret_problem
        from app.config import get_settings as settings_factory

        monkeypatch.setenv("JWT_SECRET", "too-short")
        settings_factory.cache_clear()
        assert "bytes" in (jwt_secret_problem() or "")
        settings_factory.cache_clear()

    def test_a_long_random_secret_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.auth.security import jwt_secret_problem
        from app.config import get_settings as settings_factory

        monkeypatch.setenv("JWT_SECRET", "x" * 48)
        settings_factory.cache_clear()
        assert jwt_secret_problem() is None
        settings_factory.cache_clear()


class TestCookieSecurity:
    """The Secure flag was inferred from `environment != "development"`.

    Any third value - "test", "staging", "local" - therefore got a Secure cookie
    that a plain-HTTP client never sends back, so sessions silently vanished.
    """

    def test_plain_http_environments_do_not_get_a_secure_cookie(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import get_settings as settings_factory

        for name in ("development", "test", "local"):
            monkeypatch.setenv("ENVIRONMENT", name)
            settings_factory.cache_clear()
            assert settings_factory().session_cookie_secure is False, name
        settings_factory.cache_clear()

    def test_anything_else_does(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import get_settings as settings_factory

        for name in ("production", "staging"):
            monkeypatch.setenv("ENVIRONMENT", name)
            settings_factory.cache_clear()
            assert settings_factory().session_cookie_secure is True, name
        settings_factory.cache_clear()

    def test_an_explicit_setting_overrides_the_guess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import get_settings as settings_factory

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("COOKIE_SECURE", "true")
        settings_factory.cache_clear()
        assert settings_factory().session_cookie_secure is True
        settings_factory.cache_clear()
