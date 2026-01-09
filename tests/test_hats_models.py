# ABOUTME: Unit tests for Hats Protocol data models
# ABOUTME: Tests HatsApprovalConfig, Proposal, ApprovalRequest, ApprovalResult

import pytest
from datetime import datetime, timedelta

from ralph_orchestrator.hats.models import (
    DecisionType,
    ProposalStatus,
    HatsApprovalConfig,
    Proposal,
    ApprovalRequest,
    ApprovalResult,
    Vote,
)


class TestDecisionType:
    """Tests for DecisionType enum."""

    def test_decision_type_values(self):
        """Test that all expected decision types exist."""
        assert DecisionType.ITERATION_APPROVAL.value == "iteration_approval"
        assert DecisionType.FILE_WRITE.value == "file_write"
        assert DecisionType.COMMAND_EXECUTION.value == "command_execution"
        assert DecisionType.COST_THRESHOLD.value == "cost_threshold"
        assert DecisionType.CUSTOM.value == "custom"

    def test_decision_type_is_string_enum(self):
        """Test that DecisionType values are strings."""
        for dt in DecisionType:
            assert isinstance(dt.value, str)


class TestProposalStatus:
    """Tests for ProposalStatus enum."""

    def test_proposal_status_values(self):
        """Test that all expected statuses exist."""
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.EXPIRED.value == "expired"


class TestHatsApprovalConfig:
    """Tests for HatsApprovalConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HatsApprovalConfig()

        assert config.enabled is False
        assert config.rpc_url == "https://mainnet.base.org"
        assert config.chain_id == 8453
        assert config.hats_contract == "0x3bc1A0Ad72417f2d411118085256fC53CBdDd137"
        assert config.ralph_proposal_contract == ""
        assert config.voting_period == 300
        assert config.poll_interval == 5
        assert config.decision_mappings == {}
        assert config.cost_threshold_trigger == 10.0
        assert config.require_signature is True

    def test_from_dict_basic(self):
        """Test creating config from dictionary."""
        data = {
            "enabled": True,
            "rpc_url": "https://custom.rpc.com",
            "chain_id": 1,
            "voting_period": 600,
        }
        config = HatsApprovalConfig.from_dict(data)

        assert config.enabled is True
        assert config.rpc_url == "https://custom.rpc.com"
        assert config.chain_id == 1
        assert config.voting_period == 600

    def test_from_dict_with_nested_contracts(self):
        """Test creating config with nested contracts section."""
        data = {
            "enabled": True,
            "contracts": {
                "hats_protocol": "0x1234567890123456789012345678901234567890",
                "ralph_proposal": "0x0987654321098765432109876543210987654321",
            },
        }
        config = HatsApprovalConfig.from_dict(data)

        assert config.hats_contract == "0x1234567890123456789012345678901234567890"
        assert config.ralph_proposal_contract == "0x0987654321098765432109876543210987654321"

    def test_from_dict_with_nested_chain(self):
        """Test creating config with nested chain section."""
        data = {
            "enabled": True,
            "chain": {
                "rpc_url": "https://nested.rpc.com",
                "chain_id": 42161,
            },
        }
        config = HatsApprovalConfig.from_dict(data)

        assert config.rpc_url == "https://nested.rpc.com"
        assert config.chain_id == 42161

    def test_from_dict_with_decision_mappings(self):
        """Test creating config with decision mappings."""
        data = {
            "enabled": True,
            "decision_mappings": {
                "iteration_approval": 123456,
                "cost_threshold": 789012,
            },
        }
        config = HatsApprovalConfig.from_dict(data)

        assert config.decision_mappings["iteration_approval"] == 123456
        assert config.decision_mappings["cost_threshold"] == 789012

    def test_from_dict_empty(self):
        """Test creating config from empty dictionary."""
        config = HatsApprovalConfig.from_dict({})
        assert config.enabled is False

    def test_from_dict_none(self):
        """Test creating config from None."""
        config = HatsApprovalConfig.from_dict(None)
        assert config.enabled is False


class TestProposal:
    """Tests for Proposal dataclass."""

    def test_default_proposal(self):
        """Test default proposal values."""
        proposal = Proposal()

        assert proposal.id is None
        assert proposal.question == ""
        assert proposal.decision_type == DecisionType.CUSTOM
        assert proposal.hat_id == 0
        assert proposal.deadline is None
        assert proposal.yes_votes == 0
        assert proposal.no_votes == 0
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.tx_hash is None
        assert isinstance(proposal.created_at, datetime)
        assert proposal.context == {}

    def test_proposal_with_values(self):
        """Test proposal with custom values."""
        deadline = datetime.now() + timedelta(hours=1)
        proposal = Proposal(
            id=1,
            question="Should we proceed?",
            decision_type=DecisionType.ITERATION_APPROVAL,
            hat_id=12345,
            deadline=deadline,
            yes_votes=5,
            no_votes=2,
            status=ProposalStatus.APPROVED,
            tx_hash="0xabc123",
        )

        assert proposal.id == 1
        assert proposal.question == "Should we proceed?"
        assert proposal.decision_type == DecisionType.ITERATION_APPROVAL
        assert proposal.hat_id == 12345
        assert proposal.deadline == deadline
        assert proposal.yes_votes == 5
        assert proposal.no_votes == 2
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.tx_hash == "0xabc123"

    def test_is_finalized_no_deadline(self):
        """Test is_finalized when no deadline set."""
        proposal = Proposal()
        assert proposal.is_finalized() is False

    def test_is_finalized_future_deadline(self):
        """Test is_finalized when deadline is in future."""
        proposal = Proposal(deadline=datetime.now() + timedelta(hours=1))
        assert proposal.is_finalized() is False

    def test_is_finalized_past_deadline(self):
        """Test is_finalized when deadline has passed."""
        proposal = Proposal(deadline=datetime.now() - timedelta(hours=1))
        assert proposal.is_finalized() is True

    def test_is_approved_yes_wins(self):
        """Test is_approved when yes votes win."""
        proposal = Proposal(yes_votes=5, no_votes=2)
        assert proposal.is_approved() is True

    def test_is_approved_no_wins(self):
        """Test is_approved when no votes win."""
        proposal = Proposal(yes_votes=2, no_votes=5)
        assert proposal.is_approved() is False

    def test_is_approved_tie(self):
        """Test is_approved when votes are tied."""
        proposal = Proposal(yes_votes=3, no_votes=3)
        assert proposal.is_approved() is False


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_default_request(self):
        """Test default request values."""
        request = ApprovalRequest(
            decision_type=DecisionType.ITERATION_APPROVAL,
            question="Test question",
        )

        assert request.decision_type == DecisionType.ITERATION_APPROVAL
        assert request.question == "Test question"
        assert request.context == {}
        assert request.timeout == 300
        assert request.hat_id_override is None

    def test_request_with_context(self):
        """Test request with context."""
        request = ApprovalRequest(
            decision_type=DecisionType.COST_THRESHOLD,
            question="Continue?",
            context={"cost": 50.0, "iteration": 10},
            timeout=600,
            hat_id_override=99999,
        )

        assert request.context["cost"] == 50.0
        assert request.context["iteration"] == 10
        assert request.timeout == 600
        assert request.hat_id_override == 99999


class TestApprovalResult:
    """Tests for ApprovalResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = ApprovalResult(approved=True)

        assert result.approved is True
        assert result.proposal_id is None
        assert result.yes_votes == 0
        assert result.no_votes == 0
        assert result.reason == ""
        assert result.tx_hash is None
        assert result.decision_type is None
        assert result.duration_seconds == 0.0

    def test_result_with_votes(self):
        """Test result with vote counts."""
        result = ApprovalResult(
            approved=True,
            proposal_id=42,
            yes_votes=10,
            no_votes=3,
            reason="Approved by hat wearers",
            tx_hash="0xdef456",
            decision_type=DecisionType.ITERATION_APPROVAL,
            duration_seconds=45.5,
        )

        assert result.proposal_id == 42
        assert result.yes_votes == 10
        assert result.no_votes == 3
        assert result.reason == "Approved by hat wearers"
        assert result.tx_hash == "0xdef456"
        assert result.decision_type == DecisionType.ITERATION_APPROVAL
        assert result.duration_seconds == 45.5


class TestVote:
    """Tests for Vote dataclass."""

    def test_default_vote(self):
        """Test vote creation."""
        vote = Vote(
            proposal_id=1,
            voter="0x1234567890123456789012345678901234567890",
            support=True,
            signature="0xsig",
        )

        assert vote.proposal_id == 1
        assert vote.voter == "0x1234567890123456789012345678901234567890"
        assert vote.support is True
        assert vote.signature == "0xsig"
        assert isinstance(vote.timestamp, datetime)
        assert vote.verified is False
        assert vote.hat_id == 0

    def test_vote_no_support(self):
        """Test vote with no support."""
        vote = Vote(
            proposal_id=2,
            voter="0x0000000000000000000000000000000000000001",
            support=False,
            signature="0xnosig",
            verified=True,
            hat_id=12345,
        )

        assert vote.support is False
        assert vote.verified is True
        assert vote.hat_id == 12345
