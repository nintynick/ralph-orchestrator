# ABOUTME: Unit tests for voting database functionality
# ABOUTME: Tests proposals and votes storage in DatabaseManager

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from ralph_orchestrator.web.database import DatabaseManager


class TestVotingDatabase:
    """Tests for proposals and votes database operations."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield DatabaseManager(db_path)

    def test_store_proposal(self, db):
        """Test storing a proposal."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xabc123",
            ipfs_cid="QmTestCID",
            question_text="Should we proceed?",
            decision_type="iteration_approval",
            context={"iteration": 5},
            required_hat_id="12345",
            deadline="2026-01-09T16:00:00",
            creator_address="0x1234567890123456789012345678901234567890",
            tx_hash="0xtx123",
        )

        proposal = db.get_proposal(1)

        assert proposal is not None
        assert proposal["id"] == 1
        assert proposal["question_hash"] == "0xabc123"
        assert proposal["ipfs_cid"] == "QmTestCID"
        assert proposal["question_text"] == "Should we proceed?"
        assert proposal["decision_type"] == "iteration_approval"
        assert proposal["context"]["iteration"] == 5
        assert proposal["required_hat_id"] == "12345"
        assert proposal["creator_address"] == "0x1234567890123456789012345678901234567890"

    def test_get_proposal_not_found(self, db):
        """Test getting non-existent proposal returns None."""
        result = db.get_proposal(999)
        assert result is None

    def test_get_proposal_by_hash(self, db):
        """Test getting proposal by question hash."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xuniquehash",
            question_text="Test question",
        )

        proposal = db.get_proposal_by_hash("0xuniquehash")

        assert proposal is not None
        assert proposal["question_hash"] == "0xuniquehash"

    def test_get_proposal_by_hash_not_found(self, db):
        """Test getting proposal by non-existent hash."""
        result = db.get_proposal_by_hash("0xnonexistent")
        assert result is None

    def test_update_proposal_status(self, db):
        """Test updating proposal status."""
        db.store_proposal(proposal_id=1, question_hash="0xtest")

        db.update_proposal_status(
            proposal_id=1,
            status="approved",
            yes_votes=10,
            no_votes=3,
        )

        proposal = db.get_proposal(1)

        assert proposal["status"] == "approved"
        assert proposal["yes_votes"] == 10
        assert proposal["no_votes"] == 3

    def test_record_vote(self, db):
        """Test recording a vote."""
        db.store_proposal(proposal_id=1, question_hash="0xtest")

        db.record_vote(
            proposal_id=1,
            voter_address="0xVoter123",
            support=True,
            signature="0xsig123",
            tx_hash="0xtx456",
        )

        votes = db.get_votes_for_proposal(1)

        assert len(votes) == 1
        assert votes[0]["voter_address"] == "0xvoter123"  # Should be lowercased
        assert votes[0]["support"] == 1  # SQLite stores as int
        assert votes[0]["signature"] == "0xsig123"
        assert votes[0]["tx_hash"] == "0xtx456"

    def test_record_vote_updates_existing(self, db):
        """Test that recording a vote updates existing vote from same address."""
        db.store_proposal(proposal_id=1, question_hash="0xtest")

        # First vote
        db.record_vote(
            proposal_id=1,
            voter_address="0xVoter123",
            support=True,
        )

        # Update vote
        db.record_vote(
            proposal_id=1,
            voter_address="0xVoter123",
            support=False,
        )

        votes = db.get_votes_for_proposal(1)

        # Should only have one vote (updated)
        assert len(votes) == 1
        assert votes[0]["support"] == 0  # Changed to False

    def test_get_votes_for_proposal_empty(self, db):
        """Test getting votes for proposal with no votes."""
        db.store_proposal(proposal_id=1, question_hash="0xtest")

        votes = db.get_votes_for_proposal(1)
        assert votes == []

    def test_get_votes_for_proposal_multiple(self, db):
        """Test getting multiple votes for a proposal."""
        db.store_proposal(proposal_id=1, question_hash="0xtest")

        db.record_vote(proposal_id=1, voter_address="0xVoter1", support=True)
        db.record_vote(proposal_id=1, voter_address="0xVoter2", support=True)
        db.record_vote(proposal_id=1, voter_address="0xVoter3", support=False)

        votes = db.get_votes_for_proposal(1)

        assert len(votes) == 3

    def test_get_voter_history(self, db):
        """Test getting voting history for an address."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xtest1",
            question_text="First proposal",
            decision_type="test",
            status="approved",
        )
        db.store_proposal(
            proposal_id=2,
            question_hash="0xtest2",
            question_text="Second proposal",
            decision_type="test",
            status="rejected",
        )

        db.record_vote(proposal_id=1, voter_address="0xVoter123", support=True)
        db.record_vote(proposal_id=2, voter_address="0xVoter123", support=False)

        history = db.get_voter_history("0xVoter123")

        assert len(history) == 2
        # Should include proposal info
        assert any(h.get("question_text") == "First proposal" for h in history)
        assert any(h.get("question_text") == "Second proposal" for h in history)

    def test_get_voter_history_empty(self, db):
        """Test getting history for address with no votes."""
        history = db.get_voter_history("0xNoVotes")
        assert history == []

    def test_get_proposal_history(self, db):
        """Test getting proposal history."""
        for i in range(5):
            db.store_proposal(
                proposal_id=i + 1,
                question_hash=f"0xhash{i}",
                question_text=f"Proposal {i}",
                status="pending" if i < 2 else "approved",
            )

        # Get all
        all_proposals = db.get_proposal_history(limit=10)
        assert len(all_proposals) == 5

        # Get with status filter
        pending = db.get_proposal_history(limit=10, status="pending")
        assert len(pending) == 2

        approved = db.get_proposal_history(limit=10, status="approved")
        assert len(approved) == 3

    def test_get_proposal_history_limit(self, db):
        """Test proposal history respects limit."""
        for i in range(10):
            db.store_proposal(
                proposal_id=i + 1,
                question_hash=f"0xhash{i}",
            )

        limited = db.get_proposal_history(limit=3)
        assert len(limited) == 3

    def test_get_proposal_cid(self, db):
        """Test getting IPFS CID for a proposal."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xtest",
            ipfs_cid="QmTestCID123",
        )

        cid = db.get_proposal_cid(1)
        assert cid == "QmTestCID123"

    def test_get_proposal_cid_not_found(self, db):
        """Test getting CID for non-existent proposal."""
        cid = db.get_proposal_cid(999)
        assert cid is None

    def test_get_proposal_cid_no_cid_stored(self, db):
        """Test getting CID when proposal has no CID."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xtest",
        )

        cid = db.get_proposal_cid(1)
        assert cid is None

    def test_proposal_context_json_parsing(self, db):
        """Test that context is properly stored and retrieved as JSON."""
        context = {
            "iteration": 10,
            "cost": 50.25,
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }

        db.store_proposal(
            proposal_id=1,
            question_hash="0xtest",
            context=context,
        )

        proposal = db.get_proposal(1)

        assert proposal["context"]["iteration"] == 10
        assert proposal["context"]["cost"] == 50.25
        assert proposal["context"]["nested"]["key"] == "value"
        assert proposal["context"]["list"] == [1, 2, 3]

    def test_store_proposal_replace(self, db):
        """Test that storing proposal with same ID replaces."""
        db.store_proposal(
            proposal_id=1,
            question_hash="0xoriginal",
            question_text="Original",
        )

        db.store_proposal(
            proposal_id=1,
            question_hash="0xupdated",
            question_text="Updated",
        )

        proposal = db.get_proposal(1)

        assert proposal["question_hash"] == "0xupdated"
        assert proposal["question_text"] == "Updated"
