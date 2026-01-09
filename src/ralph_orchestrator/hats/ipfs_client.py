# ABOUTME: IPFS client for storing and retrieving proposal content
# ABOUTME: Uses Pinata as the IPFS pinning service with local caching

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class IPFSConfig:
    """Configuration for IPFS integration."""

    enabled: bool = False
    provider: str = "pinata"  # pinata or web3storage
    gateway_url: str = "https://gateway.pinata.cloud/ipfs"
    pinata_api_key: Optional[str] = None
    pinata_secret_key: Optional[str] = None
    cache_ttl: int = 3600  # 1 hour cache
    cache_dir: Optional[str] = None  # Local cache directory

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IPFSConfig":
        """Create config from dictionary."""
        if not data:
            return cls()

        return cls(
            enabled=data.get("enabled", False),
            provider=data.get("provider", "pinata"),
            gateway_url=data.get("gateway_url", "https://gateway.pinata.cloud/ipfs"),
            pinata_api_key=data.get("pinata_api_key")
            or os.environ.get("PINATA_API_KEY"),
            pinata_secret_key=data.get("pinata_secret_key")
            or os.environ.get("PINATA_SECRET_KEY"),
            cache_ttl=data.get("cache_ttl", 3600),
            cache_dir=data.get("cache_dir"),
        )


@dataclass
class ProposalContent:
    """Content structure stored in IPFS."""

    version: str = "1.0"
    question: str = ""
    decision_type: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    creator_address: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "question": self.question,
            "decision_type": self.decision_type,
            "context": self.context,
            "created_at": self.created_at or datetime.now().isoformat(),
            "creator_address": self.creator_address,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProposalContent":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            question=data.get("question", ""),
            decision_type=data.get("decision_type", ""),
            context=data.get("context", {}),
            created_at=data.get("created_at", ""),
            creator_address=data.get("creator_address"),
        )


class IPFSClient:
    """Client for IPFS operations using Pinata."""

    def __init__(self, config: IPFSConfig):
        """Initialize IPFS client.

        Args:
            config: IPFS configuration
        """
        self.config = config
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}  # CID -> (timestamp, content)

        # Setup cache directory
        if config.cache_dir:
            self._cache_path = Path(config.cache_dir)
        else:
            self._cache_path = Path.home() / ".ralph" / "ipfs_cache"
        self._cache_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"IPFSClient initialized (provider={config.provider}, "
            f"cache_dir={self._cache_path})"
        )

    async def upload_proposal_content(
        self,
        question: str,
        decision_type: str,
        context: Optional[Dict[str, Any]] = None,
        creator_address: Optional[str] = None,
    ) -> str:
        """Upload proposal question and metadata to IPFS.

        Args:
            question: The proposal question text
            decision_type: Type of decision (e.g., "iteration_approval")
            context: Optional additional context
            creator_address: Optional creator Ethereum address

        Returns:
            CID (content identifier) of the uploaded content
        """
        content = ProposalContent(
            question=question,
            decision_type=decision_type,
            context=context or {},
            created_at=datetime.now().isoformat(),
            creator_address=creator_address,
        )

        content_dict = content.to_dict()
        content_json = json.dumps(content_dict, sort_keys=True)

        if self.config.provider == "pinata":
            cid = await self._upload_to_pinata(content_json, content_dict)
        else:
            raise ValueError(f"Unsupported IPFS provider: {self.config.provider}")

        # Cache the content locally
        self._cache_content(cid, content_dict)

        logger.info(f"Uploaded proposal content to IPFS: {cid}")
        return cid

    async def _upload_to_pinata(
        self, content_json: str, content_dict: Dict[str, Any]
    ) -> str:
        """Upload content to Pinata.

        Args:
            content_json: JSON string of content
            content_dict: Content as dictionary

        Returns:
            CID from Pinata
        """
        try:
            import aiohttp
        except ImportError as e:
            raise ImportError(
                "aiohttp package required for IPFS integration. "
                "Install with: pip install aiohttp"
            ) from e

        if not self.config.pinata_api_key or not self.config.pinata_secret_key:
            raise ValueError(
                "Pinata API key and secret required. "
                "Set PINATA_API_KEY and PINATA_SECRET_KEY environment variables."
            )

        url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
        headers = {
            "Content-Type": "application/json",
            "pinata_api_key": self.config.pinata_api_key,
            "pinata_secret_api_key": self.config.pinata_secret_key,
        }

        payload = {
            "pinataContent": content_dict,
            "pinataMetadata": {
                "name": f"ralph-proposal-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload, timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Pinata upload failed ({response.status}): {error_text}"
                    )

                data = await response.json()
                return data["IpfsHash"]

    async def get_proposal_content(self, cid: str) -> Optional[Dict[str, Any]]:
        """Retrieve proposal content from IPFS.

        Uses local cache first, then fetches from gateway.

        Args:
            cid: IPFS content identifier

        Returns:
            Content dictionary or None if not found
        """
        # Check memory cache
        if cid in self._cache:
            timestamp, content = self._cache[cid]
            if time.time() - timestamp < self.config.cache_ttl:
                logger.debug(f"Cache hit for {cid}")
                return content

        # Check file cache
        cached = self._load_from_cache(cid)
        if cached:
            self._cache[cid] = (time.time(), cached)
            return cached

        # Fetch from gateway
        try:
            content = await self._fetch_from_gateway(cid)
            if content:
                self._cache_content(cid, content)
                return content
        except Exception as e:
            logger.warning(f"Failed to fetch from IPFS gateway: {e}")

        return None

    async def _fetch_from_gateway(self, cid: str) -> Optional[Dict[str, Any]]:
        """Fetch content from IPFS gateway.

        Args:
            cid: IPFS content identifier

        Returns:
            Content dictionary or None
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed, cannot fetch from IPFS")
            return None

        url = f"{self.config.gateway_url}/{cid}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.json()
                    logger.debug(f"Fetched {cid} from gateway")
                    return content
                else:
                    logger.warning(
                        f"Gateway returned {response.status} for {cid}"
                    )
                    return None

    def _cache_content(self, cid: str, content: Dict[str, Any]) -> None:
        """Cache content locally.

        Args:
            cid: Content identifier
            content: Content to cache
        """
        # Memory cache
        self._cache[cid] = (time.time(), content)

        # File cache
        cache_file = self._cache_path / f"{cid}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump({"cached_at": time.time(), "content": content}, f)
        except Exception as e:
            logger.warning(f"Failed to write cache file: {e}")

    def _load_from_cache(self, cid: str) -> Optional[Dict[str, Any]]:
        """Load content from file cache.

        Args:
            cid: Content identifier

        Returns:
            Content or None if not cached/expired
        """
        cache_file = self._cache_path / f"{cid}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)

            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at < self.config.cache_ttl:
                return data.get("content")
            else:
                # Expired, remove file
                cache_file.unlink(missing_ok=True)
                return None
        except Exception as e:
            logger.warning(f"Failed to read cache file: {e}")
            return None

    def content_hash(self, content: Dict[str, Any]) -> bytes:
        """Compute keccak256 hash of content for on-chain verification.

        Args:
            content: Content dictionary

        Returns:
            32-byte hash matching Solidity keccak256
        """
        try:
            from eth_utils import keccak
        except ImportError:
            # Fallback to hashlib if eth_utils not available
            content_json = json.dumps(content, sort_keys=True)
            return hashlib.sha256(content_json.encode()).digest()

        # Hash the question text to match on-chain questionHash
        question = content.get("question", "")
        return keccak(text=question)

    def verify_content_hash(
        self, content: Dict[str, Any], expected_hash: bytes
    ) -> bool:
        """Verify that content matches expected hash.

        Args:
            content: Content dictionary
            expected_hash: Expected hash from on-chain

        Returns:
            True if hashes match
        """
        computed = self.content_hash(content)
        return computed == expected_hash

    def clear_cache(self) -> int:
        """Clear all cached content.

        Returns:
            Number of cache entries cleared
        """
        count = len(self._cache)
        self._cache.clear()

        # Clear file cache
        for cache_file in self._cache_path.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass

        logger.info(f"Cleared {count} cache entries")
        return count
