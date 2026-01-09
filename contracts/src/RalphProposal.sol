// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title RalphProposal
/// @notice On-chain voting contract for Ralph Orchestrator human-in-the-loop approvals
/// @dev Integrates with Hats Protocol to verify voter eligibility

interface IHats {
    function isWearerOfHat(address _wearer, uint256 _hatId) external view returns (bool);
    function balanceOf(address _account, uint256 _hatId) external view returns (uint256);
}

contract RalphProposal {
    /// @notice Reference to the Hats Protocol contract
    IHats public immutable hats;

    /// @notice Proposal data structure
    struct Proposal {
        bytes32 questionHash;      // Keccak256 hash of the question text
        uint256 requiredHatId;     // Hat ID required to vote
        uint256 yesVotes;          // Count of yes votes
        uint256 noVotes;           // Count of no votes
        uint256 deadline;          // Voting deadline (block timestamp)
        bool executed;             // Whether result has been finalized
        address creator;           // Address that created the proposal
    }

    /// @notice Total number of proposals created
    uint256 public proposalCount;

    /// @notice Mapping of proposal ID to proposal data
    mapping(uint256 => Proposal) public proposals;

    /// @notice Mapping of proposal ID => voter address => has voted
    mapping(uint256 => mapping(address => bool)) public hasVoted;

    /// @notice Emitted when a new proposal is created
    event ProposalCreated(
        uint256 indexed proposalId,
        bytes32 questionHash,
        uint256 hatId,
        uint256 deadline,
        address creator
    );

    /// @notice Emitted when a vote is cast
    event VoteCast(
        uint256 indexed proposalId,
        address indexed voter,
        bool support,
        uint256 hatId
    );

    /// @notice Emitted when a proposal is executed/finalized
    event ProposalExecuted(
        uint256 indexed proposalId,
        bool approved,
        uint256 yesVotes,
        uint256 noVotes
    );

    /// @notice Error thrown when voting period has ended
    error VotingEnded();

    /// @notice Error thrown when voter has already voted
    error AlreadyVoted();

    /// @notice Error thrown when voter is not wearing required hat
    error NotHatWearer();

    /// @notice Error thrown when voting period has not ended
    error VotingNotEnded();

    /// @notice Error thrown when proposal does not exist
    error ProposalNotFound();

    /// @param _hatsAddress Address of the Hats Protocol contract
    constructor(address _hatsAddress) {
        require(_hatsAddress != address(0), "Invalid Hats address");
        hats = IHats(_hatsAddress);
    }

    /// @notice Create a new proposal for voting
    /// @param questionHash Keccak256 hash of the question text
    /// @param requiredHatId Hat ID required to vote on this proposal
    /// @param votingPeriod Duration of voting period in seconds
    /// @return proposalId The ID of the created proposal
    function createProposal(
        bytes32 questionHash,
        uint256 requiredHatId,
        uint256 votingPeriod
    ) external returns (uint256 proposalId) {
        require(votingPeriod > 0, "Invalid voting period");
        require(votingPeriod <= 7 days, "Voting period too long");

        proposalId = ++proposalCount;

        proposals[proposalId] = Proposal({
            questionHash: questionHash,
            requiredHatId: requiredHatId,
            yesVotes: 0,
            noVotes: 0,
            deadline: block.timestamp + votingPeriod,
            executed: false,
            creator: msg.sender
        });

        emit ProposalCreated(
            proposalId,
            questionHash,
            requiredHatId,
            block.timestamp + votingPeriod,
            msg.sender
        );
    }

    /// @notice Cast a vote on a proposal
    /// @param proposalId ID of the proposal to vote on
    /// @param support True for yes, false for no
    function vote(uint256 proposalId, bool support) external {
        Proposal storage p = proposals[proposalId];

        if (p.deadline == 0) revert ProposalNotFound();
        if (block.timestamp >= p.deadline) revert VotingEnded();
        if (hasVoted[proposalId][msg.sender]) revert AlreadyVoted();
        if (!hats.isWearerOfHat(msg.sender, p.requiredHatId)) revert NotHatWearer();

        hasVoted[proposalId][msg.sender] = true;

        if (support) {
            p.yesVotes++;
        } else {
            p.noVotes++;
        }

        emit VoteCast(proposalId, msg.sender, support, p.requiredHatId);
    }

    /// @notice Get the result of a proposal
    /// @param proposalId ID of the proposal
    /// @return approved Whether the proposal passed (yes > no)
    /// @return yesVotes Number of yes votes
    /// @return noVotes Number of no votes
    /// @return finalized Whether voting has ended
    function getProposalResult(uint256 proposalId)
        external
        view
        returns (
            bool approved,
            uint256 yesVotes,
            uint256 noVotes,
            bool finalized
        )
    {
        Proposal storage p = proposals[proposalId];

        if (p.deadline == 0) revert ProposalNotFound();

        finalized = block.timestamp >= p.deadline;
        yesVotes = p.yesVotes;
        noVotes = p.noVotes;
        approved = yesVotes > noVotes;
    }

    /// @notice Execute/finalize a proposal after voting ends
    /// @param proposalId ID of the proposal to execute
    /// @return approved Whether the proposal passed
    function executeProposal(uint256 proposalId) external returns (bool approved) {
        Proposal storage p = proposals[proposalId];

        if (p.deadline == 0) revert ProposalNotFound();
        if (block.timestamp < p.deadline) revert VotingNotEnded();

        if (!p.executed) {
            p.executed = true;
            approved = p.yesVotes > p.noVotes;

            emit ProposalExecuted(proposalId, approved, p.yesVotes, p.noVotes);
        } else {
            approved = p.yesVotes > p.noVotes;
        }
    }

    /// @notice Check if an address can vote on a proposal
    /// @param proposalId ID of the proposal
    /// @param voter Address to check
    /// @return canVote Whether the address can vote
    /// @return reason Human-readable reason if cannot vote
    function canVote(uint256 proposalId, address voter)
        external
        view
        returns (bool canVote, string memory reason)
    {
        Proposal storage p = proposals[proposalId];

        if (p.deadline == 0) {
            return (false, "Proposal not found");
        }
        if (block.timestamp >= p.deadline) {
            return (false, "Voting ended");
        }
        if (hasVoted[proposalId][voter]) {
            return (false, "Already voted");
        }
        if (!hats.isWearerOfHat(voter, p.requiredHatId)) {
            return (false, "Not wearing required hat");
        }

        return (true, "");
    }

    /// @notice Get proposal details
    /// @param proposalId ID of the proposal
    /// @return questionHash Hash of the question
    /// @return requiredHatId Required hat ID to vote
    /// @return yesVotes Current yes votes
    /// @return noVotes Current no votes
    /// @return deadline Voting deadline timestamp
    /// @return executed Whether proposal has been executed
    /// @return creator Address that created the proposal
    function getProposal(uint256 proposalId)
        external
        view
        returns (
            bytes32 questionHash,
            uint256 requiredHatId,
            uint256 yesVotes,
            uint256 noVotes,
            uint256 deadline,
            bool executed,
            address creator
        )
    {
        Proposal storage p = proposals[proposalId];
        return (
            p.questionHash,
            p.requiredHatId,
            p.yesVotes,
            p.noVotes,
            p.deadline,
            p.executed,
            p.creator
        );
    }

    /// @notice Get the remaining time for voting on a proposal
    /// @param proposalId ID of the proposal
    /// @return remainingTime Seconds remaining, or 0 if ended
    function getRemainingTime(uint256 proposalId) external view returns (uint256 remainingTime) {
        Proposal storage p = proposals[proposalId];

        if (p.deadline == 0 || block.timestamp >= p.deadline) {
            return 0;
        }

        return p.deadline - block.timestamp;
    }
}
