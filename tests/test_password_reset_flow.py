from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH_DIR = ROOT / "frontend" / "src" / "app" / "(auth)"


def test_login_page_links_to_password_reset():
    login_page = (AUTH_DIR / "login" / "page.tsx").read_text(encoding="utf-8")

    assert 'href="/forgot-password"' in login_page


def test_password_reset_pages_use_authjs_recovery_flow():
    forgot_page = (AUTH_DIR / "forgot-password" / "page.tsx").read_text(encoding="utf-8")
    reset_page = (AUTH_DIR / "reset-password" / "page.tsx").read_text(encoding="utf-8")

    assert "/api/auth/forgot-password" in forgot_page
    assert "/api/auth/reset-password" in reset_page
    assert "password" in reset_page


def test_password_inputs_have_visibility_toggles():
    login_page = (AUTH_DIR / "login" / "page.tsx").read_text(encoding="utf-8")
    register_page = (AUTH_DIR / "register" / "page.tsx").read_text(encoding="utf-8")

    assert "Show password" in login_page
    assert "Show password" in register_page
