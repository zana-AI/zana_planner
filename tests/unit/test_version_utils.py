import pytest

from utils.version import _parse_version_tag, _format_version, get_version


@pytest.mark.unit
def test_parse_version_tag_accepts_common_formats():
    assert _parse_version_tag("v1.2.3") == (1, 2, 3)
    assert _parse_version_tag("1.2.3") == (1, 2, 3)
    assert _parse_version_tag("v10.0.1") == (10, 0, 1)
    assert _parse_version_tag("release-2-3-4") == (2, 3, 4)
    assert _parse_version_tag("v7") == (7, 0, 0)


@pytest.mark.unit
def test_format_version_outputs_v_prefix():
    assert _format_version(1, 0, 0) == "v1.0.0"


@pytest.mark.unit
def test_get_version_prefers_env(monkeypatch):
    monkeypatch.setenv("BOT_VERSION", "2.5.9")
    assert get_version() == "v2.5.9"
