from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_container_has_no_desktop_width_cap():
    styles = (ROOT / "frontend/src/app/globals.css").read_text(encoding="utf-8")
    container = styles.split(".container {", 1)[1].split("}", 1)[0]

    assert "max-width" not in container


def test_dashboard_main_has_no_desktop_width_cap():
    styles = (ROOT / "frontend/src/app/dashboard/dashboard.module.css").read_text(encoding="utf-8")
    main = styles.split(".main {", 1)[1].split("}", 1)[0]

    assert "max-width" not in main
