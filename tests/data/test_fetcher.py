"""Tests for DataFetcher."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from quantsys.data.sources.akshare import AKShareSource
from quantsys.data.fetcher import DataFetcher


@pytest.fixture
def fetcher():
    """Create a DataFetcher with temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = AKShareSource(rate_limit=0.1, retry_count=1)
        yield DataFetcher(source, Path(tmpdir))


class TestDataFetcher:
    def test_init(self, fetcher):
        """Test fetcher initialization."""
        assert fetcher.source is not None
        assert fetcher.cache is not None
        assert fetcher.cache_dir.exists()

    def test_cache_dir_created(self, fetcher):
        """Test cache directory structure is created."""
        assert fetcher.cache_dir.exists()

    def test_get_source(self, fetcher):
        """Test source is correctly configured."""
        source = fetcher.source
        assert source.name == "akshare"
        assert source.rate_limit == 0.1
