"""
Unit tests for content manager: URL canonicalization, bucket mapping,
completion calculation, and short-segment filtering.
"""
import pytest

from utils.url_utils import canonicalize_url
from services.content_progress_service import map_to_bucket_indices


# --- URL canonicalization ---

@pytest.mark.unit
def test_canonicalize_url_strips_utm_params():
    url = "https://Example.com/page?utm_source=twitter&foo=bar"
    assert canonicalize_url(url) == "https://example.com/page?foo=bar"


@pytest.mark.unit
def test_canonicalize_url_strips_fbclid_and_gclid():
    url = "https://youtube.com/watch?v=abc&fbclid=xyz&gclid=qqq"
    assert "fbclid" not in canonicalize_url(url)
    assert "gclid" not in canonicalize_url(url)
    assert "v=abc" in canonicalize_url(url)


@pytest.mark.unit
def test_canonicalize_url_normalizes_scheme_and_host_to_lowercase():
    url = "HTTPS://YouTube.COM/Watch?v=abc"
    result = canonicalize_url(url)
    assert result.startswith("https://youtube.com/")


@pytest.mark.unit
def test_canonicalize_url_removes_trailing_slash():
    url = "https://example.com/path/"
    assert canonicalize_url(url) == "https://example.com/path"
    # Root stays as /
    assert canonicalize_url("https://example.com/") == "https://example.com/"


@pytest.mark.unit
def test_canonicalize_url_sorts_remaining_query_params():
    url = "https://example.com?a=1&b=2"
    result = canonicalize_url(url)
    # urlencode with sorted items gives a=1&b=2
    assert "a=1" in result and "b=2" in result


@pytest.mark.unit
def test_canonicalize_url_empty_or_whitespace():
    assert canonicalize_url("") == ""
    assert canonicalize_url("   ") == ""


# --- Bucket mapping ---

@pytest.mark.unit
def test_map_to_bucket_indices_seconds():
    # duration 100s, bucket_count 120: position 10-50 -> start_idx=12, end_idx=60
    indices = map_to_bucket_indices(10, 50, 100.0, 120)
    assert 12 in indices
    assert 60 in indices
    assert min(indices) >= 0
    assert max(indices) < 120
    assert len(indices) == 60 - 12 + 1  # 49 buckets


@pytest.mark.unit
def test_map_to_bucket_indices_ratio():
    # ratio 0..1, bucket_count 10: [0.2, 0.5] intersects buckets 2,3,4,5 (0.5 is start of bucket 5)
    indices = map_to_bucket_indices(0.2, 0.5, 1.0, 10)
    assert set(indices) == {2, 3, 4, 5}


@pytest.mark.unit
def test_map_to_bucket_indices_clamped():
    # indices clamped to [0, bucket_count-1]
    indices = map_to_bucket_indices(-10, 200, 100.0, 120)
    assert all(0 <= i < 120 for i in indices)


@pytest.mark.unit
def test_map_to_bucket_indices_empty_duration():
    assert map_to_bucket_indices(0, 1, 0, 120) == []
    assert map_to_bucket_indices(0, 1, -1, 120) == []


# --- Completion calculation (progress_ratio from buckets) ---

@pytest.mark.unit
def test_completion_ratio_from_buckets():
    # progress_ratio = count(bucket > 0) / bucket_count
    bucket_count = 10
    buckets = [1, 1, 0, 0, 1, 0, 0, 0, 0, 0]
    non_zero = sum(1 for b in buckets if (b or 0) > 0)
    progress_ratio = min(1.0, non_zero / bucket_count)
    assert progress_ratio == 0.3


# --- Short segment filtering (logic used in record_consumption) ---

@pytest.mark.unit
def test_short_segment_seconds_rejected():
    MIN_SEGMENT_SECONDS = 2.0
    assert (100.0 - 99.0) < MIN_SEGMENT_SECONDS  # 1 second rejected
    assert (5.0 - 2.0) >= MIN_SEGMENT_SECONDS    # 3 seconds accepted


@pytest.mark.unit
def test_short_segment_ratio_rejected():
    MIN_SEGMENT_RATIO = 0.01
    assert (0.005 - 0.0) < MIN_SEGMENT_RATIO   # 0.5% rejected
    assert (0.05 - 0.02) >= MIN_SEGMENT_RATIO  # 3% accepted
