from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_browser_supabase_client_uses_session_only_cookie():
    client = (ROOT / "frontend/src/lib/supabase/client.ts").read_text(encoding="utf-8")

    assert "cookieOptions: { maxAge: undefined }" in client


def test_server_supabase_client_uses_session_only_cookie():
    server = (ROOT / "frontend/src/lib/supabase/server.ts").read_text(encoding="utf-8")

    assert "cookieOptions: { maxAge: undefined }" in server
    assert "cookieStore.set(name, value, options)" in server


def test_proxy_uses_session_only_cookie():
    proxy = (ROOT / "frontend/src/proxy.ts").read_text(encoding="utf-8")

    assert "cookieOptions: { maxAge: undefined }" in proxy
    assert "supabaseResponse.cookies.set(name, value, options)" in proxy
