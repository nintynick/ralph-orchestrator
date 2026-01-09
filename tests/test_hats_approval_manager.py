# ABOUTME: Unit tests for HatsApprovalManager
# ABOUTME: Tests approval flow, hat ID lookups, and result handling with mocks

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from ralph_orchestrator.hats.models import (
    DecisionType,
    ProposalStatus,
    HatsApprovalConfig,
    ApprovalRequest,
    ApprovalResult,
)
from ralph_orchestrator.hats.approval_manager import (
    HatsApprovalManager,
    check_iteration_approval,
    check_cost_threshold_approval,
)


@pytest.fixture
def basic_config():
    """Create a basic Hats approval config for testing."""
    return HatsApprovalConfig(
        enabled=True,
        rpc_url="https://mainnet.base.org",
        chain_id=8453,
        ralph_proposal_contract="0x1234567890123456789012345678901234567890",
        voting_period=60,
        poll_interval=1,
        decision_mappings={
            "iteration_approval": 100,
            "cost_threshold": 200,
            "file_write": 300,
        },
        cost_threshold_trigger=10.0,
    )


@pytest.fixture
def manager_with_mock_client(basic_config):
    """Create a HatsApprovalManager with mocked client."""
    manager = HatsApprovalManager(basic_config)

    # Mock the contract client
    manager.client = MagicMock()
    manager.client.is_wearer_of_hat = MagicMock(return_value=True)
    manager.client.create_proposal = AsyncMock(return_value=(1, "0xabc123"))
    manager.client.get_proposal_result = MagicMock(return_value=(True, 5, 2, True))

    return manager


class TestHatsApprovalManagerInit:
    """Tests for HatsApprovalManager initialization."""

    def test_init_with_config(self, basic_config):
        """Test manager initialization with config."""
        with patch(
            "ralph_orchestrator.hats.approval_manager.HatsContractClient"
        ) as mock_client:
            manager = HatsApprovalManager(basic_config)

            assert manager.config == basic_config
            assert manager.domain.chain_id == 8453
            assert manager.domain.verifying_contract == basic_config.ralph_proposal_contract
            mock_client.assert_called_once()

    def test_init_pending_proposals_empty(self, basic_config):
        """Test that pending proposals starts empty."""
        with patch("ralph_orchestrator.hats.approval_manager.HatsContractClient"):
            manager = HatsApprovalManager(basic_config)
            assert len(manager._pending_proposals) == 0

    def test_init_approval_history_empty(self, basic_config):
        """Test that approval history starts empty."""
        with patch("ralph_orchestrator.hats.approval_manager.HatsContractClient"):
            manager = HatsApprovalManager(basic_config)
            assert len(manager._approval_history) == 0


class TestGetHatIdForDecision:
    """Tests for get_hat_id_for_decision method."""

    def test_get_configured_hat_id(self, manager_with_mock_client):
        """Test getting hat ID for configured decision type."""
        hat_id = manager_with_mock_client.get_hat_id_for_decision(
            DecisionType.ITERATION_APPROVAL
        )
        assert hat_id == 100

    def test_get_unconfigured_hat_id(self, manager_with_mock_client):
        """Test getting hat ID for unconfigured decision type."""
        hat_id = manager_with_mock_client.get_hat_id_for_decision(
            DecisionType.COMMAND_EXECUTION
        )
        assert hat_id is None

    def test_is_decision_type_configured_true(self, manager_with_mock_client):
        """Test checking if decision type is configured - true case."""
        assert manager_with_mock_client.is_decision_type_configured(
            DecisionType.ITERATION_APPROVAL
        )

    def test_is_decision_type_configured_false(self, manager_with_mock_client):
        """Test checking if decision type is configured - false case."""
        assert not manager_with_mock_client.is_decision_type_configured(
            DecisionType.COMMAND_EXECUTION
        )


class TestRequestApproval:
    """Tests for request_approval method."""

    @pytest.mark.asyncio
    async def test_auto_approve_unconfigured_decision(self, manager_with_mock_client):
        """Test auto-approval when decision type has no hat configured."""
        request = ApprovalRequest(
            decision_type=DecisionType.COMMAND_EXECUTION,  # Not in mappings
            question="Execute command?",
        )

        result = await manager_with_mock_client.request_approval(request)

        assert result.approved is True
        assert "No hat ID configured" in result.reason
        manager_with_mock_client.client.create_proposal.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_with_hat_override(self, manager_with_mock_client):
        """Test approval with hat ID override."""
        request = ApprovalRequest(
            decision_type=DecisionType.CUSTOM,
            question="Custom decision?",
            hat_id_override=999,  # Override hat ID
        )

        result = await manager_with_mock_client.request_approval(request)

        # Should use override hat ID
        manager_with_mock_client.client.create_proposal.assert_called_once()
        call_args = manager_with_mock_client.client.create_proposal.call_args
        assert call_args[1]["hat_id"] == 999

    @pytest.mark.asyncio
    async def test_approval_records_history(self, manager_with_mock_client):
        """Test that approval requests are recorded in history."""
        request = ApprovalRequest(
            decision_type=DecisionType.ITERATION_APPROVAL,
            question="Continue?",
        )

        await manager_with_mock_client.request_approval(request)

        history = manager_with_mock_client.get_approval_history()
        assert len(history) == 1
        assert history[0][0] == request

    @pytest.mark.asyncio
    async def test_approved_proposal_result(self, manager_with_mock_client):
        """Test handling approved proposal."""
        manager_with_mock_client.client.get_proposal_result.return_value = (
            True,
            5,
            2,
            True,
        )

        request = ApprovalRequest(
            decision_type=DecisionType.ITERATION_APPROVAL,
            question="Proceed?",
        )

        result = await manager_with_mock_client.request_approval(request)

        assert result.approved is True
        assert result.yes_votes == 5
        assert result.no_votes == 2
        assert result.proposal_id == 1

    @pytest.mark.asyncio
    async def test_rejected_proposal_result(self, manager_with_mock_client):
        """Test handling rejected proposal."""
        manager_with_mock_client.client.get_proposal_result.return_value = (
            False,
            2,
            5,
            True,
        )

        request = ApprovalRequest(
            decision_type=DecisionType.ITERATION_APPROVAL,
            question="Proceed?",
        )

        result = await manager_with_mock_client.request_approval(request)

        assert result.approved is False
        assert result.yes_votes == 2
        assert result.no_votes == 5

    @pytest.mark.asyncio
    async def test_no_contract_configured(self, basic_config):
        """Test error when no contract address configured."""
        config = HatsApprovalConfig(
            enabled=True,
            ralph_proposal_contract="",  # No contract
            decision_mappings={"iteration_approval": 100},
        )

        with patch("ralph_orchestrator.hats.approval_manager.HatsContractClient"):
            manager = HatsApprovalManager(config)

            request = ApprovalRequest(
                decision_type=DecisionType.ITERATION_APPROVAL,
                question="Test?",
            )

            result = await manager.request_approval(request)

            assert result.approved is False
            assert "not configured" in result.reason


class TestVerifyVoter:
    """Tests for verify_voter method."""

    def test_verify_valid_voter(self, manager_with_mock_client):
        """Test verifying a valid hat wearer."""
        manager_with_mock_client.client.is_wearer_of_hat.return_value = True

        result = manager_with_mock_client.verify_voter(
            "0x1234567890123456789012345678901234567890", 100
        )

        assert result is True
        manager_with_mock_client.client.is_wearer_of_hat.assert_called_once_with(
            "0x1234567890123456789012345678901234567890", 100
        )

    def test_verify_invalid_voter(self, manager_with_mock_client):
        """Test verifying a non-hat wearer."""
        manager_with_mock_client.client.is_wearer_of_hat.return_value = False

        result = manager_with_mock_client.verify_voter(
            "0x0000000000000000000000000000000000000001", 100
        )

        assert result is False


class TestGetPendingProposals:
    """Tests for get_pending_proposals method."""

    def test_get_pending_proposals_empty(self, manager_with_mock_client):
        """Test getting pending proposals when none exist."""
        proposals = manager_with_mock_client.get_pending_proposals()
        assert proposals == []

    def test_get_pending_proposals_with_items(self, manager_with_mock_client):
        """Test getting pending proposals when some exist."""
        from ralph_orchestrator.hats.models import Proposal

        proposal = Proposal(id=1, question="Test?", status=ProposalStatus.PENDING)
        manager_with_mock_client._pending_proposals[1] = proposal

        proposals = manager_with_mock_client.get_pending_proposals()

        assert len(proposals) == 1
        assert proposals[0].id == 1


class TestGetStats:
    """Tests for get_stats method."""

    def test_stats_empty(self, manager_with_mock_client):
        """Test stats with no history."""
        stats = manager_with_mock_client.get_stats()

        assert stats["total_requests"] == 0
        assert stats["approved"] == 0
        assert stats["rejected"] == 0
        assert stats["approval_rate"] == 0
        assert stats["avg_duration_seconds"] == 0
        assert stats["pending_proposals"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_history(self, manager_with_mock_client):
        """Test stats with approval history."""
        # Make some approval requests
        request1 = ApprovalRequest(
            decision_type=DecisionType.ITERATION_APPROVAL,
            question="Test 1?",
        )
        request2 = ApprovalRequest(
            decision_type=DecisionType.COST_THRESHOLD,
            question="Test 2?",
        )

        # First approved
        manager_with_mock_client.client.get_proposal_result.return_value = (
            True,
            5,
            2,
            True,
        )
        await manager_with_mock_client.request_approval(request1)

        # Second rejected
        manager_with_mock_client.client.get_proposal_result.return_value = (
            False,
            1,
            5,
            True,
        )
        await manager_with_mock_client.request_approval(request2)

        stats = manager_with_mock_client.get_stats()

        assert stats["total_requests"] == 2
        assert stats["approved"] == 1
        assert stats["rejected"] == 1
        assert stats["approval_rate"] == 0.5


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_check_iteration_approval(self, manager_with_mock_client):
        """Test check_iteration_approval convenience function."""
        manager_with_mock_client.client.get_proposal_result.return_value = (
            True,
            3,
            0,
            True,
        )

        result = await check_iteration_approval(
            manager_with_mock_client, iteration=5, context={"extra": "data"}
        )

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_cost_threshold_approval(self, manager_with_mock_client):
        """Test check_cost_threshold_approval convenience function."""
        manager_with_mock_client.client.get_proposal_result.return_value = (
            True,
            2,
            1,
            True,
        )

        result = await check_cost_threshold_approval(
            manager_with_mock_client,
            current_cost=25.0,
            threshold=10.0,
        )

        assert result.approved is True
