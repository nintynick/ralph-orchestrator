# ABOUTME: Unit tests for IPFS client functionality
# ABOUTME: Tests IPFSConfig, IPFSClient, and ProposalContent

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from ralph_orchestrator.hats.ipfs_client import (
    IPFSConfig,
    IPFSClient,
    ProposalContent,
)


class TestIPFSConfig:
    """Tests for IPFSConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = IPFSConfig()

        assert config.enabled is False
        assert config.provider == "pinata"
        assert config.gateway_url == "https://gateway.pinata.cloud/ipfs"
        assert config.pinata_api_key is None
        assert config.pinata_secret_key is None
        assert config.cache_ttl == 3600
        assert config.cache_dir is None

    def test_from_dict_basic(self):
        """Test creating config from dictionary."""
        data = {
            "enabled": True,
            "provider": "web3storage",
            "gateway_url": "https://custom.gateway.com/ipfs",
            "cache_ttl": 7200,
        }
        config = IPFSConfig.from_dict(data)

        assert config.enabled is True
        assert config.provider == "web3storage"
        assert config.gateway_url == "https://custom.gateway.com/ipfs"
        assert config.cache_ttl == 7200

    def test_from_dict_empty(self):
        """Test creating config from empty dictionary."""
        config = IPFSConfig.from_dict({})
        assert config.enabled is False

    def test_from_dict_none(self):
        """Test creating config from None."""
        config = IPFSConfig.from_dict(None)
        assert config.enabled is False

    def test_from_dict_with_env_vars(self):
        """Test that env vars are checked when keys not in dict."""
        with patch.dict(
            "os.environ",
            {"PINATA_API_KEY": "test_key", "PINATA_SECRET_KEY": "test_secret"},
        ):
            config = IPFSConfig.from_dict({"enabled": True})

            assert config.pinata_api_key == "test_key"
            assert config.pinata_secret_key == "test_secret"


class TestProposalContent:
    """Tests for ProposalContent dataclass."""

    def test_default_content(self):
        """Test default content values."""
        content = ProposalContent()

        assert content.version == "1.0"
        assert content.question == ""
        assert content.decision_type == ""
        assert content.context == {}
        assert content.created_at == ""
        assert content.creator_address is None

    def test_content_with_values(self):
        """Test content with custom values."""
        content = ProposalContent(
            question="Should we proceed?",
            decision_type="iteration_approval",
            context={"iteration": 5},
            created_at="2026-01-09T15:00:00",
            creator_address="0x1234",
        )

        assert content.question == "Should we proceed?"
        assert content.decision_type == "iteration_approval"
        assert content.context["iteration"] == 5

    def test_to_dict(self):
        """Test converting content to dictionary."""
        content = ProposalContent(
            question="Test question",
            decision_type="cost_threshold",
            context={"cost": 50.0},
        )
        result = content.to_dict()

        assert result["version"] == "1.0"
        assert result["question"] == "Test question"
        assert result["decision_type"] == "cost_threshold"
        assert result["context"]["cost"] == 50.0
        assert "created_at" in result

    def test_from_dict(self):
        """Test creating content from dictionary."""
        data = {
            "version": "2.0",
            "question": "Parsed question",
            "decision_type": "custom",
            "context": {"key": "value"},
            "created_at": "2026-01-09T12:00:00",
            "creator_address": "0xabcd",
        }
        content = ProposalContent.from_dict(data)

        assert content.version == "2.0"
        assert content.question == "Parsed question"
        assert content.decision_type == "custom"
        assert content.context["key"] == "value"
        assert content.creator_address == "0xabcd"


class TestIPFSClient:
    """Tests for IPFSClient class."""

    def test_init_creates_cache_dir(self):
        """Test that initialization creates cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "ipfs_cache"
            config = IPFSConfig(enabled=True, cache_dir=str(cache_dir))
            client = IPFSClient(config)

            assert cache_dir.exists()

    def test_cache_content(self):
        """Test caching content locally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            test_content = {"question": "Test?", "decision_type": "test"}
            client._cache_content("QmTest123", test_content)

            # Check memory cache
            assert "QmTest123" in client._cache

            # Check file cache
            cache_file = Path(tmpdir) / "QmTest123.json"
            assert cache_file.exists()

    def test_load_from_cache(self):
        """Test loading content from file cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir, cache_ttl=3600)
            client = IPFSClient(config)

            # Write cache file
            import time

            cache_data = {
                "cached_at": time.time(),
                "content": {"question": "Cached question"},
            }
            cache_file = Path(tmpdir) / "QmCached.json"
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            # Load from cache
            result = client._load_from_cache("QmCached")

            assert result is not None
            assert result["question"] == "Cached question"

    def test_load_from_cache_expired(self):
        """Test that expired cache returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir, cache_ttl=1)
            client = IPFSClient(config)

            # Write expired cache file
            import time

            cache_data = {
                "cached_at": time.time() - 100,  # 100 seconds ago
                "content": {"question": "Old question"},
            }
            cache_file = Path(tmpdir) / "QmExpired.json"
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            # Load from cache should return None
            result = client._load_from_cache("QmExpired")
            assert result is None

    def test_clear_cache(self):
        """Test clearing the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            # Add some cached content
            client._cache_content("QmTest1", {"q": "1"})
            client._cache_content("QmTest2", {"q": "2"})

            assert len(client._cache) == 2

            # Clear cache
            count = client.clear_cache()

            assert len(client._cache) == 0
            assert count >= 2

    @pytest.mark.asyncio
    async def test_upload_requires_credentials(self):
        """Test that upload fails without credentials."""
        config = IPFSConfig(enabled=True, provider="pinata")
        client = IPFSClient(config)

        with pytest.raises(ValueError, match="Pinata API key"):
            await client.upload_proposal_content(
                question="Test",
                decision_type="test",
            )

    @pytest.mark.asyncio
    async def test_upload_success(self):
        """Test successful upload with mocked response."""
        pytest.importorskip("aiohttp")
        import aiohttp

        config = IPFSConfig(
            enabled=True,
            provider="pinata",
            pinata_api_key="test_key",
            pinata_secret_key="test_secret",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config.cache_dir = tmpdir
            client = IPFSClient(config)

            mock_json_result = {"IpfsHash": "QmTestCID123"}

            # Create a class that properly implements async context manager
            class MockResponse:
                status = 200

                async def json(self):
                    return mock_json_result

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            class MockSession:
                def post(self, *args, **kwargs):
                    return MockResponse()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            with patch.object(aiohttp, "ClientSession", return_value=MockSession()):
                cid = await client.upload_proposal_content(
                    question="Should we proceed?",
                    decision_type="iteration_approval",
                    context={"iteration": 5},
                )

            assert cid == "QmTestCID123"
            assert "QmTestCID123" in client._cache

    @pytest.mark.asyncio
    async def test_get_proposal_content_from_cache(self):
        """Test getting content from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            # Pre-populate cache
            test_content = {"question": "Cached", "decision_type": "test"}
            client._cache_content("QmCached123", test_content)

            # Get from cache
            result = await client.get_proposal_content("QmCached123")

            assert result is not None
            assert result["question"] == "Cached"

    @pytest.mark.asyncio
    async def test_get_proposal_content_from_gateway(self):
        """Test fetching content from IPFS gateway."""
        pytest.importorskip("aiohttp")
        import aiohttp

        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            expected_content = {"question": "From gateway", "decision_type": "test"}

            # Create a class that properly implements async context manager
            class MockResponse:
                status = 200

                async def json(self):
                    return expected_content

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            class MockSession:
                def get(self, *args, **kwargs):
                    return MockResponse()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            with patch.object(aiohttp, "ClientSession", return_value=MockSession()):
                result = await client.get_proposal_content("QmGateway123")

            assert result is not None
            assert result["question"] == "From gateway"

    def test_content_hash(self):
        """Test computing content hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            content = {"question": "Test question"}
            hash_result = client.content_hash(content)

            assert isinstance(hash_result, bytes)
            assert len(hash_result) == 32  # 256 bits = 32 bytes

    def test_verify_content_hash(self):
        """Test verifying content hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = IPFSConfig(enabled=True, cache_dir=tmpdir)
            client = IPFSClient(config)

            content = {"question": "Test question"}
            expected_hash = client.content_hash(content)

            assert client.verify_content_hash(content, expected_hash) is True
            assert (
                client.verify_content_hash(content, b"wrong_hash_________________")
                is False
            )
