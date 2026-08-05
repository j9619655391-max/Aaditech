"""Tests for the Microsoft/Azure OAuth2 helpers (SSO + Graph email) in
app/ms_oauth.py — implemented with Python stdlib so they run offline with
no fastapi/httpx/msal installed. The token-exchange and Graph /sendMail
calls themselves need a live Azure tenant (documented in DEPLOYMENT.md); the
pure logic (id_token decoding, group→role mapping) and the "no config -> no
network call" guard are exercised here.

Pure stdlib — run with: pytest, or directly via
`PYTHONPATH=. python3 tests/test_sso_email.py`"""
import base64
import json
import sys

sys.path.insert(0, ".")

from app import ms_oauth  # noqa: E402


def _id_token(claims: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.sig"


def test_decode_id_token_returns_claims():
    claims = {"email": "eng@aaditech.local", "groups": ["g-admin"]}
    decoded = ms_oauth.decode_id_token(_id_token(claims))
    assert decoded["email"] == "eng@aaditech.local"
    assert decoded["groups"] == ["g-admin"]


def _patch_settings(**values):
    """Temporarily replace ms_oauth.settings with a fake object (avoids the
    lazy __getattr__ import of app.config when using mock.patch)."""
    import contextlib

    real = ms_oauth.settings

    class _Fake:
        pass

    fake = _Fake()
    for k, v in values.items():
        setattr(fake, k, v)

    @contextlib.contextmanager
    def _ctx():
        ms_oauth.settings = fake
        try:
            yield fake
        finally:
            ms_oauth.settings = real

    return _ctx()


_roleset = _patch_settings  # convenience alias


def test_roles_default_viewer_and_engineer():
    with _roleset(azure_admin_group_ids=""):
        assert set(ms_oauth.roles_from_claims({"email": "x@aaditech.local"})) == {
            "viewer",
            "support_engineer",
        }


def test_admin_group_grants_cleanup_approver():
    with _roleset(azure_admin_group_ids="g-admin, g-other"):
        assert "cleanup_approver" in ms_oauth.roles_from_claims({"groups": ["g-admin"]})


def test_non_admin_group_does_not_grant_approver():
    with _roleset(azure_admin_group_ids="g-admin"):
        assert "cleanup_approver" not in ms_oauth.roles_from_claims({"groups": ["unrelated"]})


def test_azure_configured_requires_all_three_values():
    with _roleset(azure_client_id="", azure_client_secret="secret", azure_tenant_id="tenant"):
        assert ms_oauth.azure_configured() is False


def test_send_graph_email_unconfigured_returns_false_without_network():
    with _roleset(azure_client_id="", azure_client_secret="", azure_tenant_id=""):
        assert ms_oauth.send_graph_email("subj", "body", ["a@aaditech.local"]) is False


if __name__ == "__main__":
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