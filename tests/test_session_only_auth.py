from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_page_is_never_redirected_for_an_authenticated_user():
    proxy = (ROOT / "frontend/src/proxy.ts").read_text(encoding="utf-8")

    assert 'pathname === "/login"' not in proxy
    assert 'pathname === "/register"' not in proxy


def test_supabase_auth_cookies_are_session_only_everywhere():
    for relative_path in (
        "frontend/src/lib/supabase/client.ts",
        "frontend/src/lib/supabase/server.ts",
        "frontend/src/proxy.ts",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "cookieOptions" in source
        assert "maxAge: undefined" in source


def test_new_browser_tabs_clear_any_stale_authenticated_session():
    guard = (ROOT / "frontend/src/components/shared/AuthSessionGuard.tsx").read_text(
        encoding="utf-8"
    )

    assert "sessionStorage" in guard
    assert "supabase.auth.signOut()" in guard

