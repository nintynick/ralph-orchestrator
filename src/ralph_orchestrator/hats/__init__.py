# ABOUTME: Hats Protocol integration for human-in-the-loop approvals
# ABOUTME: Exports HatsApprovalManager and related models for on-chain voting

from .models import (
    DecisionType,
    ProposalStatus,
    HatsApprovalConfig,
    Proposal,
    ApprovalRequest,
    ApprovalResult,
)
from .approval_manager import HatsApprovalManager
from .ipfs_client import IPFSClient, IPFSConfig, ProposalContent

__all__ = [
    "DecisionType",
    "ProposalStatus",
    "HatsApprovalConfig",
    "Proposal",
    "ApprovalRequest",
    "ApprovalResult",
    "HatsApprovalManager",
    "IPFSClient",
    "IPFSConfig",
    "ProposalContent",
]
