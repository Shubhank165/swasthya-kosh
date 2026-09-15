"""Provisioning the kiosk token: where it lives, when it is refused, and what off looks like."""

from __future__ import annotations

import os

import pytest

from medikiosk.config import Settings
from medikiosk.providers.intake_api import load_token

TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_an_unprovisioned_kiosk_has_no_token_rather_than_an_error(tmp_path) -> None:
    """No token means every document stays on the Jetson - the kiosk's original behaviour."""

    assert load_token(tmp_path / "does-not-exist") is None


def test_the_token_is_read_and_trimmed(tmp_path) -> None:
    """Editors and `echo` leave a trailing newline, which would otherwise ride in the header."""

    path = tmp_path / "kiosk_token"
    path.write_text(TOKEN + "\n")
    if os.name == "posix":
        path.chmod(0o600)
    assert load_token(path) == TOKEN


def test_an_empty_token_file_is_treated_as_unprovisioned(tmp_path) -> None:
    path = tmp_path / "kiosk_token"
    path.write_text("   \n")
    if os.name == "posix":
        path.chmod(0o600)
    assert load_token(path) is None


def test_a_home_relative_path_is_expanded(tmp_path, monkeypatch) -> None:
    """The configured default is ~/.config/..., which means nothing until it is expanded."""

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    target = tmp_path / ".config" / "medikiosk" / "kiosk_token"
    target.parent.mkdir(parents=True)
    target.write_text(TOKEN)
    if os.name == "posix":
        target.chmod(0o600)
    assert load_token("~/.config/medikiosk/kiosk_token") == TOKEN


@pytest.mark.skipif(os.name != "posix", reason="group/other permission bits are POSIX-only")
@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
def test_a_token_others_can_read_is_refused(tmp_path, mode) -> None:
    """A readable token is a copyable credential for a hospital's records. Refuse, loudly."""

    path = tmp_path / "kiosk_token"
    path.write_text(TOKEN)
    path.chmod(mode)
    with pytest.raises(PermissionError) as raised:
        load_token(path)
    # The error has to be actionable, and it must not become the leak it is guarding against.
    assert "chmod 600" in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_cloud_ocr_is_off_unless_turned_on() -> None:
    """It needs internet and sends images out of the building. Neither should happen by default."""

    assert Settings().handwritten_cloud_ocr is False


def test_the_default_token_location_is_outside_the_kiosk_tree() -> None:
    """Anything under the kiosk directory is one careless `git add` away from being published."""

    location = str(Settings().intake_token_path).replace("\\", "/")
    assert location.startswith("~/.config/")
    assert "medikiosk/src" not in location
