import pytest

from services.gcp_tts_service import GcpTtsService


@pytest.mark.unit
def test_normalize_language_code_maps_supported_locales():
    assert GcpTtsService.normalize_language_code("fa") == "fa-IR"
    assert GcpTtsService.normalize_language_code("fa-IR") == "fa-IR"
    assert GcpTtsService.normalize_language_code("fr") == "fr-FR"
    assert GcpTtsService.normalize_language_code("fr-FR") == "fr-FR"
    assert GcpTtsService.normalize_language_code("en") == "en-US"
    assert GcpTtsService.normalize_language_code("de-DE") == "en-US"
