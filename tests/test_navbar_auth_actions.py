from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_link_is_available_in_both_authentication_states():
    navbar = (ROOT / "frontend/src/components/shared/Navbar.tsx").read_text(encoding="utf-8")

    authenticated_branch = navbar.split("{user ? (", 1)[1].split(") : (", 1)[0]
    signed_out_branch = navbar.split(") : (", 1)[1].split("</div>", 1)[0]

    assert 'href="/login"' in authenticated_branch
    assert 'href="/login"' in signed_out_branch

