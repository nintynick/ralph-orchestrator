# ABOUTME: EIP-712 signature verification for hat wearer authentication
# ABOUTME: Verifies that voters are legitimate hat wearers using typed signatures

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .contract_client import HatsContractClient

logger = logging.getLogger(__name__)


@dataclass
class EIP712Domain:
    """EIP-712 domain parameters for Ralph voting."""

    name: str = "RalphOrchestrator"
    version: str = "1"
    chain_id: int = 8453  # Base mainnet
    verifying_contract: str = ""


@dataclass
class EIP712Authenticator:
    """Handles EIP-712 signature verification for hat wearers.

    This class generates typed data for voting messages and verifies
    that signatures come from addresses that wear the required hat.
    """

    domain: EIP712Domain
    hats_client: "HatsContractClient"
    _nonces: Dict[str, int] = field(default_factory=dict)

    # EIP-712 type definitions for voting
    VOTE_TYPES = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Vote": [
            {"name": "proposalId", "type": "uint256"},
            {"name": "support", "type": "bool"},
            {"name": "voter", "type": "address"},
            {"name": "nonce", "type": "uint256"},
        ],
    }

    def get_typed_data(
        self, proposal_id: int, support: bool, voter: str
    ) -> Dict[str, Any]:
        """Generate EIP-712 typed data for signing a vote.

        Args:
            proposal_id: ID of the proposal being voted on
            support: True for yes, False for no
            voter: Address of the voter

        Returns:
            Typed data structure for signing with eth_signTypedData_v4
        """
        try:
            from eth_utils import to_checksum_address
        except ImportError:
            # Fallback if eth_utils not available
            to_checksum_address = lambda x: x

        nonce = self._nonces.get(voter.lower(), 0)

        return {
            "types": self.VOTE_TYPES,
            "primaryType": "Vote",
            "domain": {
                "name": self.domain.name,
                "version": self.domain.version,
                "chainId": self.domain.chain_id,
                "verifyingContract": to_checksum_address(self.domain.verifying_contract)
                if self.domain.verifying_contract
                else "0x0000000000000000000000000000000000000000",
            },
            "message": {
                "proposalId": proposal_id,
                "support": support,
                "voter": to_checksum_address(voter),
                "nonce": nonce,
            },
        }

    def get_signing_message(
        self, proposal_id: int, support: bool, voter: str
    ) -> str:
        """Get a human-readable message describing what is being signed.

        Args:
            proposal_id: ID of the proposal
            support: Vote direction
            voter: Voter address

        Returns:
            Human-readable message for display
        """
        vote_str = "YES" if support else "NO"
        return (
            f"Vote {vote_str} on Ralph Proposal #{proposal_id}\n"
            f"Voter: {voter}\n"
            f"Chain: {self.domain.chain_id} (Base)"
        )

    def verify_vote_signature(
        self,
        proposal_id: int,
        support: bool,
        voter: str,
        signature: str,
        required_hat_id: int,
    ) -> bool:
        """Verify a vote signature and hat wearer status.

        Args:
            proposal_id: ID of the proposal
            support: Vote direction (True = yes, False = no)
            voter: Claimed voter address
            signature: EIP-712 signature (hex string)
            required_hat_id: Hat ID required to vote

        Returns:
            True if signature is valid AND voter wears the required hat
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_typed_data
            from eth_utils import to_checksum_address
        except ImportError as e:
            logger.error(f"Missing eth-account package: {e}")
            return False

        try:
            # Get typed data for verification
            typed_data = self.get_typed_data(proposal_id, support, voter)

            # Encode and recover signer
            signable = encode_typed_data(full_message=typed_data)
            recovered = Account.recover_message(signable, signature=signature)

            # Verify recovered address matches claimed voter
            if recovered.lower() != voter.lower():
                logger.warning(
                    f"Signature recovery mismatch: recovered={recovered}, claimed={voter}"
                )
                return False

            # Verify hat wearer status on-chain
            is_wearer = self.hats_client.is_wearer_of_hat(voter, required_hat_id)
            if not is_wearer:
                logger.warning(
                    f"Address {voter} is not wearing hat {required_hat_id}"
                )
                return False

            # Increment nonce on successful verification to prevent replay
            self._nonces[voter.lower()] = self._nonces.get(voter.lower(), 0) + 1

            logger.info(
                f"Vote verified: proposal={proposal_id}, voter={voter}, support={support}"
            )
            return True

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def get_nonce(self, voter: str) -> int:
        """Get the current nonce for a voter address.

        Args:
            voter: Voter address

        Returns:
            Current nonce (0 if never voted)
        """
        return self._nonces.get(voter.lower(), 0)

    def reset_nonce(self, voter: str) -> None:
        """Reset the nonce for a voter (for testing).

        Args:
            voter: Voter address
        """
        if voter.lower() in self._nonces:
            del self._nonces[voter.lower()]


def create_vote_signature(
    private_key: str,
    proposal_id: int,
    support: bool,
    voter: str,
    domain: EIP712Domain,
    nonce: int = 0,
) -> str:
    """Create an EIP-712 signature for a vote (utility function for testing/CLI).

    Args:
        private_key: Private key to sign with (hex string)
        proposal_id: ID of the proposal
        support: True for yes, False for no
        voter: Voter address
        domain: EIP-712 domain parameters
        nonce: Nonce for replay protection

    Returns:
        Signature as hex string
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        from eth_utils import to_checksum_address
    except ImportError as e:
        raise ImportError(
            "eth-account package required. Install with: pip install eth-account"
        ) from e

    typed_data = {
        "types": EIP712Authenticator.VOTE_TYPES,
        "primaryType": "Vote",
        "domain": {
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "verifyingContract": to_checksum_address(domain.verifying_contract)
            if domain.verifying_contract
            else "0x0000000000000000000000000000000000000000",
        },
        "message": {
            "proposalId": proposal_id,
            "support": support,
            "voter": to_checksum_address(voter),
            "nonce": nonce,
        },
    }

    signable = encode_typed_data(full_message=typed_data)
    account = Account.from_key(private_key)
    signed = account.sign_message(signable)

    return signed.signature.hex()
