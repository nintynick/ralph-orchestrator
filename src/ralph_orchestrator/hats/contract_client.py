# ABOUTME: Web3 client for interacting with Hats and RalphProposal contracts
# ABOUTME: Handles proposal creation, voting, and result retrieval on Base chain

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from .models import HatsApprovalConfig

logger = logging.getLogger(__name__)

# Load .env file if it exists (for RALPH_HATS_PRIVATE_KEY)
try:
    from dotenv import load_dotenv

    # Look for .env in current directory and parent directories
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
        logger.debug(f"Loaded environment from {env_file.absolute()}")
    else:
        # Try to find .env in common locations
        for search_path in [Path.cwd(), Path.cwd().parent, Path.home()]:
            candidate = search_path / ".env"
            if candidate.exists():
                load_dotenv(candidate)
                logger.debug(f"Loaded environment from {candidate}")
                break
except ImportError:
    # python-dotenv not installed, rely on environment being set externally
    pass

# Contract ABIs (minimal required functions)
RALPH_PROPOSAL_ABI = [
    {
        "inputs": [
            {"name": "questionHash", "type": "bytes32"},
            {"name": "requiredHatId", "type": "uint256"},
            {"name": "votingPeriod", "type": "uint256"},
            {"name": "ipfsCid", "type": "string"},
        ],
        "name": "createProposal",
        "outputs": [{"name": "proposalId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "proposalId", "type": "uint256"},
            {"name": "support", "type": "bool"},
        ],
        "name": "vote",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "getProposalResult",
        "outputs": [
            {"name": "approved", "type": "bool"},
            {"name": "yesVotes", "type": "uint256"},
            {"name": "noVotes", "type": "uint256"},
            {"name": "finalized", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "proposals",
        "outputs": [
            {"name": "questionHash", "type": "bytes32"},
            {"name": "requiredHatId", "type": "uint256"},
            {"name": "yesVotes", "type": "uint256"},
            {"name": "noVotes", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "executed", "type": "bool"},
            {"name": "creator", "type": "address"},
            {"name": "ipfsCid", "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "proposalCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "proposalId", "type": "uint256"},
            {"indexed": False, "name": "questionHash", "type": "bytes32"},
            {"indexed": False, "name": "hatId", "type": "uint256"},
            {"indexed": False, "name": "deadline", "type": "uint256"},
            {"indexed": False, "name": "creator", "type": "address"},
            {"indexed": False, "name": "ipfsCid", "type": "string"},
        ],
        "name": "ProposalCreated",
        "type": "event",
    },
]

HATS_ABI = [
    {
        "inputs": [
            {"name": "_wearer", "type": "address"},
            {"name": "_hatId", "type": "uint256"},
        ],
        "name": "isWearerOfHat",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_account", "type": "address"},
            {"name": "_hatId", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "_hatId", "type": "uint256"}],
        "name": "isActive",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class HatsContractClient:
    """Client for interacting with Hats Protocol contracts on Base chain."""

    def __init__(
        self, config: HatsApprovalConfig, private_key: Optional[str] = None
    ):
        """Initialize the contract client.

        Args:
            config: Hats configuration with RPC URL and contract addresses
            private_key: Optional private key for signing transactions.
                         If not provided, will try RALPH_HATS_PRIVATE_KEY env var.
        """
        self.config = config
        self._web3 = None
        self._proposal_contract = None
        self._hats_contract = None
        self._account = None

        # Get private key from parameter or environment
        self._private_key = private_key or os.environ.get("RALPH_HATS_PRIVATE_KEY")

    def _ensure_initialized(self):
        """Lazy initialization of Web3 and contracts."""
        if self._web3 is not None:
            return

        try:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware
        except ImportError as e:
            raise ImportError(
                "web3 package required for Hats integration. "
                "Install with: pip install 'ralph-orchestrator[hats]'"
            ) from e

        self._web3 = Web3(Web3.HTTPProvider(self.config.rpc_url))

        # Add POA middleware for Base chain
        self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self._web3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {self.config.rpc_url}")

        # Initialize contracts
        if self.config.ralph_proposal_contract:
            self._proposal_contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(self.config.ralph_proposal_contract),
                abi=RALPH_PROPOSAL_ABI,
            )

        self._hats_contract = self._web3.eth.contract(
            address=Web3.to_checksum_address(self.config.hats_contract),
            abi=HATS_ABI,
        )

        # Initialize account if private key provided
        if self._private_key:
            from eth_account import Account

            self._account = Account.from_key(self._private_key)
            logger.info(f"Initialized account: {self._account.address}")

    @property
    def web3(self):
        """Get Web3 instance, initializing if needed."""
        self._ensure_initialized()
        return self._web3

    @property
    def account_address(self) -> Optional[str]:
        """Get the account address if configured."""
        if self._account:
            return self._account.address
        return None

    def is_wearer_of_hat(self, address: str, hat_id: int) -> bool:
        """Check if an address is wearing a specific hat.

        This checks all three conditions:
        1. Address holds the hat token
        2. Hat is active
        3. Wearer is eligible

        Args:
            address: Ethereum address to check
            hat_id: Hat ID to check

        Returns:
            True if the address is wearing the hat
        """
        self._ensure_initialized()

        try:
            from web3 import Web3

            result = self._hats_contract.functions.isWearerOfHat(
                Web3.to_checksum_address(address), hat_id
            ).call()
            logger.debug(f"isWearerOfHat({address}, {hat_id}) = {result}")
            return result
        except Exception as e:
            logger.error(f"Error checking hat wearer status: {e}")
            return False

    def is_hat_active(self, hat_id: int) -> bool:
        """Check if a hat is active.

        Args:
            hat_id: Hat ID to check

        Returns:
            True if the hat is active
        """
        self._ensure_initialized()

        try:
            result = self._hats_contract.functions.isActive(hat_id).call()
            return result
        except Exception as e:
            logger.error(f"Error checking hat active status: {e}")
            return False

    async def create_proposal(
        self, question: str, hat_id: int, voting_period: int, ipfs_cid: Optional[str] = None
    ) -> Tuple[int, str]:
        """Create an on-chain proposal.

        Args:
            question: The question to vote on
            hat_id: Required hat ID for voters
            voting_period: Voting period in seconds
            ipfs_cid: Optional IPFS CID for proposal content

        Returns:
            Tuple of (proposal_id, tx_hash)

        Raises:
            ValueError: If no private key configured
            RuntimeError: If transaction fails
        """
        self._ensure_initialized()

        if not self._account:
            raise ValueError(
                "Private key required for creating proposals. "
                "Set RALPH_HATS_PRIVATE_KEY environment variable."
            )

        if not self._proposal_contract:
            raise ValueError(
                "RalphProposal contract address not configured. "
                "Set ralph_proposal_contract in hats_approval config."
            )

        from web3 import Web3

        # Hash the question
        question_hash = Web3.keccak(text=question)

        try:
            # Build transaction
            tx = self._proposal_contract.functions.createProposal(
                question_hash, hat_id, voting_period, ipfs_cid or ""
            ).build_transaction(
                {
                    "from": self._account.address,
                    "nonce": self._web3.eth.get_transaction_count(
                        self._account.address
                    ),
                    "gas": 300000,  # Increased for string storage
                    "maxFeePerGas": self._web3.eth.gas_price * 2,
                    "maxPriorityFeePerGas": self._web3.eth.gas_price // 10,
                }
            )

            # Sign and send
            signed_tx = self._web3.eth.account.sign_transaction(
                tx, self._account.key
            )
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(f"Proposal creation tx sent: {tx_hash.hex()}")

            # Wait for receipt
            receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] != 1:
                raise RuntimeError(f"Transaction failed: {receipt}")

            # Extract proposal ID from logs
            proposal_id = self._extract_proposal_id(receipt)

            logger.info(f"Proposal {proposal_id} created (tx: {tx_hash.hex()})")
            return proposal_id, tx_hash.hex()

        except Exception as e:
            logger.error(f"Failed to create proposal: {e}")
            raise RuntimeError(f"Failed to create proposal: {e}") from e

    def _extract_proposal_id(self, receipt) -> int:
        """Extract proposal ID from transaction receipt logs."""
        if not self._proposal_contract:
            return 0

        try:
            # Look for ProposalCreated event
            logs = self._proposal_contract.events.ProposalCreated().process_receipt(
                receipt
            )
            if logs:
                return logs[0]["args"]["proposalId"]
        except Exception as e:
            logger.warning(f"Could not extract proposal ID from logs: {e}")

        # Fallback: read proposalCount from contract (it equals the last ID created)
        try:
            proposal_count = self._proposal_contract.functions.proposalCount().call()
            logger.info(f"Using proposalCount fallback: {proposal_count}")
            return proposal_count
        except Exception as e:
            logger.warning(f"Could not get proposalCount: {e}")
            return 0

    def get_proposal_result(
        self, proposal_id: int
    ) -> Tuple[bool, int, int, bool]:
        """Get the result of a proposal.

        Args:
            proposal_id: ID of the proposal

        Returns:
            Tuple of (approved, yes_votes, no_votes, finalized)
        """
        self._ensure_initialized()

        if not self._proposal_contract:
            raise ValueError("RalphProposal contract not configured")

        logger.debug(f"Getting result for proposal_id={proposal_id} (type={type(proposal_id).__name__})")

        try:
            result = self._proposal_contract.functions.getProposalResult(
                int(proposal_id)  # Ensure it's an int
            ).call()
            logger.debug(f"Proposal {proposal_id} result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error getting proposal result for ID {proposal_id}: {e}")
            raise

    def get_proposal_count(self) -> int:
        """Get the total number of proposals created.

        Returns:
            Total proposal count
        """
        self._ensure_initialized()

        if not self._proposal_contract:
            raise ValueError("RalphProposal contract not configured")

        return self._proposal_contract.functions.proposalCount().call()

    def get_proposal_details(self, proposal_id: int) -> dict:
        """Get detailed information about a proposal.

        Args:
            proposal_id: ID of the proposal

        Returns:
            Dictionary with proposal details
        """
        self._ensure_initialized()

        if not self._proposal_contract:
            raise ValueError("RalphProposal contract not configured")

        try:
            result = self._proposal_contract.functions.proposals(proposal_id).call()
            return {
                "question_hash": result[0].hex(),
                "required_hat_id": result[1],
                "yes_votes": result[2],
                "no_votes": result[3],
                "deadline": result[4],
                "executed": result[5],
                "creator": result[6],
                "ipfs_cid": result[7] if len(result) > 7 else "",
            }
        except Exception as e:
            logger.error(f"Error getting proposal details: {e}")
            raise

    async def vote(self, proposal_id: int, support: bool) -> str:
        """Vote on a proposal.

        Args:
            proposal_id: ID of the proposal to vote on
            support: True for yes, False for no

        Returns:
            Transaction hash

        Raises:
            ValueError: If no private key configured
            RuntimeError: If transaction fails
        """
        self._ensure_initialized()

        if not self._account:
            raise ValueError(
                "Private key required for voting. "
                "Set RALPH_HATS_PRIVATE_KEY environment variable."
            )

        if not self._proposal_contract:
            raise ValueError("RalphProposal contract not configured")

        try:
            # Build transaction
            tx = self._proposal_contract.functions.vote(
                proposal_id, support
            ).build_transaction(
                {
                    "from": self._account.address,
                    "nonce": self._web3.eth.get_transaction_count(
                        self._account.address
                    ),
                    "gas": 100000,
                    "maxFeePerGas": self._web3.eth.gas_price * 2,
                    "maxPriorityFeePerGas": self._web3.eth.gas_price // 10,
                }
            )

            # Sign and send
            signed_tx = self._web3.eth.account.sign_transaction(
                tx, self._account.key
            )
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(f"Vote tx sent: {tx_hash.hex()}")

            # Wait for receipt
            receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] != 1:
                raise RuntimeError(f"Vote transaction failed: {receipt}")

            logger.info(f"Vote recorded for proposal {proposal_id} (support={support})")
            return tx_hash.hex()

        except Exception as e:
            logger.error(f"Failed to vote: {e}")
            raise RuntimeError(f"Failed to vote: {e}") from e

    def estimate_gas_cost(self, gas_used: int) -> float:
        """Estimate the cost in ETH for a given gas amount.

        Args:
            gas_used: Amount of gas

        Returns:
            Cost in ETH
        """
        self._ensure_initialized()

        gas_price = self._web3.eth.gas_price
        return self._web3.from_wei(gas_used * gas_price, "ether")
