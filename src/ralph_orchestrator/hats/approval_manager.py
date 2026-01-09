# ABOUTME: Main HatsApprovalManager class for human-in-the-loop approvals
# ABOUTME: Integrates with orchestrator loop for on-chain voting decision gates

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from .models import (
    HatsApprovalConfig,
    Proposal,
    ProposalStatus,
    DecisionType,
    ApprovalRequest,
    ApprovalResult,
)
from .contract_client import HatsContractClient
from .eip712_auth import EIP712Authenticator, EIP712Domain
from .ipfs_client import IPFSClient, IPFSConfig

logger = logging.getLogger(__name__)


class HatsApprovalManager:
    """Manages human-in-the-loop approvals using Hats Protocol.

    This class handles:
    - Creating on-chain proposals for decisions requiring approval
    - Polling for vote results
    - Verifying hat wearer status for voters

    Follows the existing permission patterns in acp_handlers.py.
    """

    def __init__(
        self,
        config: HatsApprovalConfig,
        private_key: Optional[str] = None,
    ):
        """Initialize the approval manager.

        Args:
            config: Hats configuration
            private_key: Optional private key for creating proposals.
                         If not provided, will try RALPH_HATS_PRIVATE_KEY env var.
        """
        self.config = config
        self.client = HatsContractClient(config, private_key)

        # Set up EIP-712 domain
        self.domain = EIP712Domain(
            name="RalphOrchestrator",
            version="1",
            chain_id=config.chain_id,
            verifying_contract=config.ralph_proposal_contract,
        )

        self.authenticator = EIP712Authenticator(
            domain=self.domain,
            hats_client=self.client,
        )

        # Initialize IPFS client if configured
        self.ipfs_client: Optional[IPFSClient] = None
        if config.ipfs and config.ipfs.enabled:
            self.ipfs_client = IPFSClient(config.ipfs)
            logger.info("IPFS client initialized for proposal content storage")

        # Track pending proposals
        self._pending_proposals: Dict[int, Proposal] = {}

        # Track approval history for auditing
        self._approval_history: list[tuple[ApprovalRequest, ApprovalResult]] = []

        logger.info(
            f"HatsApprovalManager initialized (chain_id={config.chain_id}, "
            f"voting_period={config.voting_period}s, ipfs={'enabled' if self.ipfs_client else 'disabled'})"
        )

    def get_hat_id_for_decision(self, decision_type: DecisionType) -> Optional[int]:
        """Get the hat ID required for a decision type.

        Args:
            decision_type: Type of decision

        Returns:
            Hat ID or None if not configured for this decision type
        """
        hat_id = self.config.decision_mappings.get(decision_type.value)
        if hat_id is not None:
            return int(hat_id)
        return None

    def is_decision_type_configured(self, decision_type: DecisionType) -> bool:
        """Check if a decision type has a hat ID configured.

        Args:
            decision_type: Type of decision

        Returns:
            True if hat ID is configured for this decision type
        """
        return self.get_hat_id_for_decision(decision_type) is not None

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Request approval for a decision via on-chain voting.

        Creates an on-chain proposal and waits for hat wearers to vote.

        Args:
            request: The approval request with decision type, question, and context

        Returns:
            ApprovalResult with the decision and vote counts
        """
        start_time = time.time()

        # Get hat ID for this decision type
        hat_id = request.hat_id_override or self.get_hat_id_for_decision(
            request.decision_type
        )

        if hat_id is None:
            # No hat configured for this decision type - auto-approve
            result = ApprovalResult(
                approved=True,
                reason=f"No hat ID configured for {request.decision_type.value}",
                decision_type=request.decision_type,
                duration_seconds=time.time() - start_time,
            )
            self._approval_history.append((request, result))
            logger.info(f"Auto-approved: {result.reason}")
            return result

        # Check if contract is configured
        if not self.config.ralph_proposal_contract:
            result = ApprovalResult(
                approved=False,
                reason="RalphProposal contract address not configured",
                decision_type=request.decision_type,
                duration_seconds=time.time() - start_time,
            )
            self._approval_history.append((request, result))
            logger.warning(f"Cannot create proposal: {result.reason}")
            return result

        # Create on-chain proposal
        try:
            # Upload to IPFS first if enabled
            ipfs_cid: Optional[str] = None
            if self.ipfs_client:
                try:
                    ipfs_cid = await self.ipfs_client.upload_proposal_content(
                        question=request.question,
                        decision_type=request.decision_type.value,
                        context=request.context,
                        creator_address=self.client.account_address,
                    )
                    logger.info(f"Uploaded proposal content to IPFS: {ipfs_cid}")
                except Exception as e:
                    # Log but don't fail - IPFS is optional
                    logger.warning(f"Failed to upload to IPFS: {e}")

            proposal_id, tx_hash = await self.client.create_proposal(
                question=request.question,
                hat_id=hat_id,
                voting_period=self.config.voting_period,
                ipfs_cid=ipfs_cid,
            )

            proposal = Proposal(
                id=proposal_id,
                question=request.question,
                ipfs_cid=ipfs_cid,
                decision_type=request.decision_type,
                hat_id=hat_id,
                deadline=datetime.now() + timedelta(seconds=self.config.voting_period),
                tx_hash=tx_hash,
                context=request.context,
            )
            self._pending_proposals[proposal_id] = proposal

            logger.info(
                f"Created proposal {proposal_id} for {request.decision_type.value} "
                f"(hat_id={hat_id}, tx={tx_hash}, ipfs={ipfs_cid or 'none'})"
            )

            # Wait for votes
            result = await self._wait_for_result(proposal, request.timeout)
            result.duration_seconds = time.time() - start_time
            result.decision_type = request.decision_type

            self._approval_history.append((request, result))
            return result

        except Exception as e:
            logger.error(f"Failed to create proposal: {e}")
            result = ApprovalResult(
                approved=False,
                reason=f"Failed to create proposal: {str(e)}",
                decision_type=request.decision_type,
                duration_seconds=time.time() - start_time,
            )
            self._approval_history.append((request, result))
            return result

    async def _wait_for_result(
        self, proposal: Proposal, timeout: int
    ) -> ApprovalResult:
        """Wait for proposal voting to complete.

        Polls the contract until voting period ends or timeout is reached.

        Args:
            proposal: The proposal to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            ApprovalResult with the final decision
        """
        start_time = time.time()
        poll_interval = self.config.poll_interval

        logger.info(
            f"Waiting for proposal {proposal.id} (timeout={timeout}s, "
            f"deadline={proposal.deadline})"
        )

        # Initial delay to let RPC propagate the new proposal state
        await asyncio.sleep(2)

        while (time.time() - start_time) < timeout:
            try:
                approved, yes_votes, no_votes, finalized = (
                    self.client.get_proposal_result(proposal.id)
                )

                # Update proposal state
                proposal.yes_votes = yes_votes
                proposal.no_votes = no_votes

                if finalized:
                    proposal.status = (
                        ProposalStatus.APPROVED if approved else ProposalStatus.REJECTED
                    )

                    # Remove from pending
                    self._pending_proposals.pop(proposal.id, None)

                    logger.info(
                        f"Proposal {proposal.id} finalized: "
                        f"{'APPROVED' if approved else 'REJECTED'} "
                        f"(yes={yes_votes}, no={no_votes})"
                    )

                    return ApprovalResult(
                        approved=approved,
                        proposal_id=proposal.id,
                        yes_votes=yes_votes,
                        no_votes=no_votes,
                        reason=f"Proposal {'approved' if approved else 'rejected'} "
                        f"by hat wearers ({yes_votes} yes, {no_votes} no)",
                        tx_hash=proposal.tx_hash,
                    )

                # Log progress
                if yes_votes > 0 or no_votes > 0:
                    logger.debug(
                        f"Proposal {proposal.id} in progress: "
                        f"yes={yes_votes}, no={no_votes}"
                    )

            except Exception as e:
                logger.warning(f"Error polling proposal result: {e}")

            await asyncio.sleep(poll_interval)

        # Timeout reached
        proposal.status = ProposalStatus.EXPIRED
        self._pending_proposals.pop(proposal.id, None)

        logger.warning(f"Proposal {proposal.id} timed out after {timeout}s")

        return ApprovalResult(
            approved=False,
            proposal_id=proposal.id,
            yes_votes=proposal.yes_votes,
            no_votes=proposal.no_votes,
            reason=f"Voting period expired without sufficient votes "
            f"(yes={proposal.yes_votes}, no={proposal.no_votes})",
            tx_hash=proposal.tx_hash,
        )

    def verify_voter(self, address: str, hat_id: int) -> bool:
        """Verify that an address is a valid hat wearer.

        Args:
            address: Address to verify
            hat_id: Required hat ID

        Returns:
            True if address wears the hat
        """
        return self.client.is_wearer_of_hat(address, hat_id)

    def get_pending_proposals(self) -> list[Proposal]:
        """Get list of pending proposals.

        Returns:
            List of proposals awaiting votes
        """
        return list(self._pending_proposals.values())

    def get_proposal(self, proposal_id: int) -> Optional[Proposal]:
        """Get a specific proposal by ID.

        Args:
            proposal_id: ID of the proposal

        Returns:
            Proposal if found, None otherwise
        """
        return self._pending_proposals.get(proposal_id)

    def get_approval_history(
        self,
    ) -> list[tuple[ApprovalRequest, ApprovalResult]]:
        """Get history of all approval requests and results.

        Returns:
            List of (request, result) tuples
        """
        return list(self._approval_history)

    def get_stats(self) -> dict:
        """Get statistics about approval requests.

        Returns:
            Dictionary with approval stats
        """
        total = len(self._approval_history)
        approved = sum(1 for _, r in self._approval_history if r.approved)
        rejected = total - approved
        avg_duration = (
            sum(r.duration_seconds for _, r in self._approval_history) / total
            if total > 0
            else 0
        )

        return {
            "total_requests": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approved / total if total > 0 else 0,
            "avg_duration_seconds": avg_duration,
            "pending_proposals": len(self._pending_proposals),
        }

    async def get_proposal_content(self, ipfs_cid: str) -> Optional[Dict]:
        """Retrieve proposal content from IPFS.

        Args:
            ipfs_cid: IPFS content identifier

        Returns:
            Content dictionary or None if not found
        """
        if not self.ipfs_client:
            return None

        return await self.ipfs_client.get_proposal_content(ipfs_cid)


async def check_iteration_approval(
    manager: HatsApprovalManager,
    iteration: int,
    context: Optional[dict] = None,
) -> ApprovalResult:
    """Convenience function to check iteration approval.

    Args:
        manager: HatsApprovalManager instance
        iteration: Current iteration number
        context: Optional additional context

    Returns:
        ApprovalResult
    """
    request = ApprovalRequest(
        decision_type=DecisionType.ITERATION_APPROVAL,
        question=f"Approve iteration {iteration} to proceed?",
        context=context or {"iteration": iteration},
    )
    return await manager.request_approval(request)


async def check_cost_threshold_approval(
    manager: HatsApprovalManager,
    current_cost: float,
    threshold: float,
    context: Optional[dict] = None,
) -> ApprovalResult:
    """Convenience function to check cost threshold approval.

    Args:
        manager: HatsApprovalManager instance
        current_cost: Current accumulated cost in USD
        threshold: Cost threshold that was exceeded
        context: Optional additional context

    Returns:
        ApprovalResult
    """
    request = ApprovalRequest(
        decision_type=DecisionType.COST_THRESHOLD,
        question=f"Cost has reached ${current_cost:.2f} (threshold: ${threshold:.2f}). "
        f"Continue execution?",
        context=context
        or {"current_cost": current_cost, "threshold": threshold},
    )
    return await manager.request_approval(request)
