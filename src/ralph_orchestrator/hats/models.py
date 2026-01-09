# ABOUTME: Data models for Hats Protocol approval system
# ABOUTME: Defines Proposal, Vote, and ApprovalResult dataclasses

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .ipfs_client import IPFSConfig


class DecisionType(str, Enum):
    """Types of decisions that require approval."""

    ITERATION_APPROVAL = "iteration_approval"
    FILE_WRITE = "file_write"
    COMMAND_EXECUTION = "command_execution"
    COST_THRESHOLD = "cost_threshold"
    CUSTOM = "custom"


class ProposalStatus(str, Enum):
    """Status of an on-chain proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class HatsApprovalConfig:
    """Configuration for Hats Protocol integration."""

    enabled: bool = False
    rpc_url: str = "https://mainnet.base.org"
    chain_id: int = 8453  # Base mainnet
    hats_contract: str = "0x3bc1A0Ad72417f2d411118085256fC53CBdDd137"
    ralph_proposal_contract: str = ""
    voting_period: int = 300  # 5 minutes default
    poll_interval: int = 5  # Seconds between checking results
    decision_mappings: Dict[str, int] = field(default_factory=dict)
    cost_threshold_trigger: float = 10.0  # USD threshold for cost approval
    require_signature: bool = True
    ipfs: Optional[Any] = None  # IPFSConfig, optional for IPFS storage

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HatsApprovalConfig":
        """Create config from dictionary (e.g., from YAML)."""
        if not data:
            return cls()

        # Handle nested contracts section
        contracts = data.get("contracts", {})

        # Handle nested chain section
        chain = data.get("chain", {})

        # Handle IPFS config
        ipfs_config = None
        if "ipfs" in data:
            from .ipfs_client import IPFSConfig

            ipfs_config = IPFSConfig.from_dict(data["ipfs"])

        return cls(
            enabled=data.get("enabled", False),
            rpc_url=chain.get("rpc_url", data.get("rpc_url", "https://mainnet.base.org")),
            chain_id=chain.get("chain_id", data.get("chain_id", 8453)),
            hats_contract=contracts.get(
                "hats_protocol",
                data.get("hats_contract", "0x3bc1A0Ad72417f2d411118085256fC53CBdDd137"),
            ),
            ralph_proposal_contract=contracts.get(
                "ralph_proposal", data.get("ralph_proposal_contract", "")
            ),
            voting_period=data.get("voting_period", 300),
            poll_interval=data.get("poll_interval", 5),
            decision_mappings=data.get("decision_mappings", {}),
            cost_threshold_trigger=data.get("cost_threshold_trigger", 10.0),
            require_signature=data.get("require_signature", True),
            ipfs=ipfs_config,
        )


@dataclass
class Proposal:
    """Represents an on-chain approval proposal."""

    id: Optional[int] = None
    question: str = ""
    question_hash: Optional[str] = None
    ipfs_cid: Optional[str] = None  # IPFS content identifier for full proposal data
    decision_type: DecisionType = DecisionType.CUSTOM
    hat_id: int = 0
    deadline: Optional[datetime] = None
    yes_votes: int = 0
    no_votes: int = 0
    status: ProposalStatus = ProposalStatus.PENDING
    tx_hash: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)

    def is_finalized(self) -> bool:
        """Check if proposal voting has ended."""
        if self.deadline is None:
            return False
        return datetime.now() >= self.deadline

    def is_approved(self) -> bool:
        """Check if proposal passed (more yes than no votes)."""
        return self.yes_votes > self.no_votes


@dataclass
class ApprovalRequest:
    """Request for human approval via Hats Protocol."""

    decision_type: DecisionType
    question: str
    context: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 300  # Seconds to wait for approval
    hat_id_override: Optional[int] = None  # Override default hat ID for this request


@dataclass
class ApprovalResult:
    """Result of an approval request."""

    approved: bool
    proposal_id: Optional[int] = None
    yes_votes: int = 0
    no_votes: int = 0
    reason: str = ""
    tx_hash: Optional[str] = None
    decision_type: Optional[DecisionType] = None
    duration_seconds: float = 0.0


@dataclass
class Vote:
    """Represents a vote on a proposal."""

    proposal_id: int
    voter: str  # Ethereum address
    support: bool  # True = yes, False = no
    signature: str  # EIP-712 signature
    timestamp: datetime = field(default_factory=datetime.now)
    verified: bool = False
    hat_id: int = 0
