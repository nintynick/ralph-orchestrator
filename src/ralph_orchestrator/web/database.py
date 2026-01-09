# ABOUTME: Database module for Ralph Orchestrator web monitoring
# ABOUTME: Provides SQLite storage for execution history and metrics

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import threading

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database for Ralph Orchestrator execution history."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file (default: ~/.ralph/history.db)
        """
        if db_path is None:
            config_dir = Path.home() / ".ralph"
            config_dir.mkdir(exist_ok=True)
            db_path = config_dir / "history.db"
        
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()
        logger.info(f"Database initialized at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Thread-safe context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create orchestrator_runs table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS orchestrator_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        orchestrator_id TEXT NOT NULL,
                        prompt_path TEXT NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        status TEXT NOT NULL,
                        total_iterations INTEGER DEFAULT 0,
                        max_iterations INTEGER,
                        error_message TEXT,
                        metadata TEXT
                    )
                """)
                
                # Create iteration_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS iteration_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL,
                        iteration_number INTEGER NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        status TEXT NOT NULL,
                        current_task TEXT,
                        agent_output TEXT,
                        error_message TEXT,
                        metrics TEXT,
                        FOREIGN KEY (run_id) REFERENCES orchestrator_runs(id)
                    )
                """)
                
                # Create task_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS task_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL,
                        task_description TEXT NOT NULL,
                        status TEXT NOT NULL,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        iteration_count INTEGER DEFAULT 0,
                        error_message TEXT,
                        FOREIGN KEY (run_id) REFERENCES orchestrator_runs(id)
                    )
                """)
                
                # Create proposals table for Hats voting
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS proposals (
                        id INTEGER PRIMARY KEY,
                        question_hash TEXT NOT NULL,
                        ipfs_cid TEXT,
                        question_text TEXT,
                        decision_type TEXT,
                        context TEXT,
                        required_hat_id TEXT,
                        deadline TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        yes_votes INTEGER DEFAULT 0,
                        no_votes INTEGER DEFAULT 0,
                        creator_address TEXT,
                        tx_hash TEXT,
                        created_at TIMESTAMP NOT NULL
                    )
                """)

                # Create votes table for Hats voting history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS votes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        proposal_id INTEGER NOT NULL,
                        voter_address TEXT NOT NULL,
                        support BOOLEAN NOT NULL,
                        signature TEXT,
                        tx_hash TEXT,
                        voted_at TIMESTAMP NOT NULL,
                        FOREIGN KEY (proposal_id) REFERENCES proposals(id),
                        UNIQUE(proposal_id, voter_address)
                    )
                """)

                # Create indices for better query performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_runs_orchestrator_id
                    ON orchestrator_runs(orchestrator_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_runs_start_time
                    ON orchestrator_runs(start_time DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_iterations_run_id
                    ON iteration_history(run_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_run_id
                    ON task_history(run_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_proposals_status
                    ON proposals(status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_proposals_deadline
                    ON proposals(deadline)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_votes_proposal
                    ON votes(proposal_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_votes_voter
                    ON votes(voter_address)
                """)

                conn.commit()
    
    def create_run(self, orchestrator_id: str, prompt_path: str, 
                   max_iterations: Optional[int] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> int:
        """Create a new orchestrator run entry.
        
        Args:
            orchestrator_id: Unique ID of the orchestrator
            prompt_path: Path to the prompt file
            max_iterations: Maximum iterations for this run
            metadata: Additional metadata to store
            
        Returns:
            ID of the created run
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO orchestrator_runs 
                    (orchestrator_id, prompt_path, start_time, status, max_iterations, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    orchestrator_id,
                    prompt_path,
                    datetime.now().isoformat(),
                    "running",
                    max_iterations,
                    json.dumps(metadata) if metadata else None
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_run_status(self, run_id: int, status: str, 
                         error_message: Optional[str] = None,
                         total_iterations: Optional[int] = None):
        """Update the status of an orchestrator run.
        
        Args:
            run_id: ID of the run to update
            status: New status (running, completed, failed, paused)
            error_message: Error message if failed
            total_iterations: Total iterations completed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                updates = ["status = ?"]
                params = [status]
                
                if status in ["completed", "failed"]:
                    updates.append("end_time = ?")
                    params.append(datetime.now().isoformat())
                
                if error_message is not None:
                    updates.append("error_message = ?")
                    params.append(error_message)
                
                if total_iterations is not None:
                    updates.append("total_iterations = ?")
                    params.append(total_iterations)
                
                params.append(run_id)
                cursor.execute(f"""
                    UPDATE orchestrator_runs 
                    SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                conn.commit()
    
    def add_iteration(self, run_id: int, iteration_number: int,
                     current_task: Optional[str] = None,
                     metrics: Optional[Dict[str, Any]] = None) -> int:
        """Add a new iteration entry.
        
        Args:
            run_id: ID of the parent run
            iteration_number: Iteration number
            current_task: Current task being executed
            metrics: Performance metrics for this iteration
            
        Returns:
            ID of the created iteration
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO iteration_history 
                    (run_id, iteration_number, start_time, status, current_task, metrics)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    iteration_number,
                    datetime.now().isoformat(),
                    "running",
                    current_task,
                    json.dumps(metrics) if metrics else None
                ))
                conn.commit()
                return cursor.lastrowid
    
    def update_iteration(self, iteration_id: int, status: str,
                        agent_output: Optional[str] = None,
                        error_message: Optional[str] = None):
        """Update an iteration entry.
        
        Args:
            iteration_id: ID of the iteration to update
            status: New status (running, completed, failed)
            agent_output: Output from the agent
            error_message: Error message if failed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE iteration_history
                    SET status = ?, end_time = ?, agent_output = ?, error_message = ?
                    WHERE id = ?
                """, (
                    status,
                    datetime.now().isoformat() if status != "running" else None,
                    agent_output,
                    error_message,
                    iteration_id
                ))
                conn.commit()
    
    def add_task(self, run_id: int, task_description: str) -> int:
        """Add a task entry.
        
        Args:
            run_id: ID of the parent run
            task_description: Description of the task
            
        Returns:
            ID of the created task
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO task_history (run_id, task_description, status)
                    VALUES (?, ?, ?)
                """, (run_id, task_description, "pending"))
                conn.commit()
                return cursor.lastrowid
    
    def update_task_status(self, task_id: int, status: str,
                          error_message: Optional[str] = None):
        """Update task status.
        
        Args:
            task_id: ID of the task to update
            status: New status (pending, in_progress, completed, failed)
            error_message: Error message if failed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                if status == "in_progress":
                    cursor.execute("""
                        UPDATE task_history
                        SET status = ?, start_time = ?
                        WHERE id = ?
                    """, (status, now, task_id))
                elif status in ["completed", "failed"]:
                    cursor.execute("""
                        UPDATE task_history
                        SET status = ?, end_time = ?, error_message = ?
                        WHERE id = ?
                    """, (status, now, error_message, task_id))
                else:
                    cursor.execute("""
                        UPDATE task_history
                        SET status = ?
                        WHERE id = ?
                    """, (status, task_id))
                
                conn.commit()
    
    def get_recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent orchestrator runs.
        
        Args:
            limit: Maximum number of runs to return
            
        Returns:
            List of run dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orchestrator_runs
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))
            
            runs = []
            for row in cursor.fetchall():
                run = dict(row)
                if run.get('metadata'):
                    run['metadata'] = json.loads(run['metadata'])
                runs.append(run)
            
            return runs
    
    def get_run_details(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific run.
        
        Args:
            run_id: ID of the run
            
        Returns:
            Run details with iterations and tasks
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get run info
            cursor.execute("SELECT * FROM orchestrator_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            run = dict(row)
            if run.get('metadata'):
                run['metadata'] = json.loads(run['metadata'])
            
            # Get iterations
            cursor.execute("""
                SELECT * FROM iteration_history
                WHERE run_id = ?
                ORDER BY iteration_number
            """, (run_id,))
            
            iterations = []
            for row in cursor.fetchall():
                iteration = dict(row)
                if iteration.get('metrics'):
                    iteration['metrics'] = json.loads(iteration['metrics'])
                iterations.append(iteration)
            
            run['iterations'] = iterations
            
            # Get tasks
            cursor.execute("""
                SELECT * FROM task_history
                WHERE run_id = ?
                ORDER BY id
            """, (run_id,))
            
            run['tasks'] = [dict(row) for row in cursor.fetchall()]
            
            return run
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Total runs
            cursor.execute("SELECT COUNT(*) FROM orchestrator_runs")
            stats['total_runs'] = cursor.fetchone()[0]
            
            # Runs by status
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM orchestrator_runs 
                GROUP BY status
            """)
            stats['runs_by_status'] = dict(cursor.fetchall())
            
            # Total iterations
            cursor.execute("SELECT COUNT(*) FROM iteration_history")
            stats['total_iterations'] = cursor.fetchone()[0]
            
            # Total tasks
            cursor.execute("SELECT COUNT(*) FROM task_history")
            stats['total_tasks'] = cursor.fetchone()[0]
            
            # Average iterations per run
            cursor.execute("""
                SELECT AVG(total_iterations) 
                FROM orchestrator_runs 
                WHERE total_iterations > 0
            """)
            result = cursor.fetchone()[0]
            stats['avg_iterations_per_run'] = round(result, 2) if result else 0
            
            # Success rate
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 / 
                    NULLIF(COUNT(*), 0)
                FROM orchestrator_runs
                WHERE status IN ('completed', 'failed')
            """)
            result = cursor.fetchone()[0]
            stats['success_rate'] = round(result, 2) if result else 0
            
            return stats
    
    def cleanup_old_records(self, days: int = 30):
        """Remove records older than specified days.
        
        Args:
            days: Number of days to keep
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get run IDs to delete (using SQLite datetime functions directly)
                cursor.execute("""
                    SELECT id FROM orchestrator_runs
                    WHERE datetime(start_time) < datetime('now', '-' || ? || ' days')
                """, (days,))
                run_ids = [row[0] for row in cursor.fetchall()]
                
                if run_ids:
                    # Delete iterations
                    cursor.execute("""
                        DELETE FROM iteration_history
                        WHERE run_id IN ({})
                    """.format(','.join('?' * len(run_ids))), run_ids)
                    
                    # Delete tasks
                    cursor.execute("""
                        DELETE FROM task_history
                        WHERE run_id IN ({})
                    """.format(','.join('?' * len(run_ids))), run_ids)
                    
                    # Delete runs
                    cursor.execute("""
                        DELETE FROM orchestrator_runs
                        WHERE id IN ({})
                    """.format(','.join('?' * len(run_ids))), run_ids)
                    
                    conn.commit()
                    logger.info(f"Cleaned up {len(run_ids)} old runs")

    # ========== Proposals and Votes Methods ==========

    def store_proposal(
        self,
        proposal_id: int,
        question_hash: str,
        ipfs_cid: Optional[str] = None,
        question_text: Optional[str] = None,
        decision_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        required_hat_id: Optional[str] = None,
        deadline: Optional[str] = None,
        creator_address: Optional[str] = None,
        tx_hash: Optional[str] = None,
        status: str = "pending",
    ) -> None:
        """Store a proposal in the database.

        Args:
            proposal_id: On-chain proposal ID
            question_hash: Hash of the question
            ipfs_cid: IPFS content identifier
            question_text: The actual question text
            decision_type: Type of decision
            context: Additional context (JSON)
            required_hat_id: Hat ID required to vote
            deadline: Voting deadline timestamp
            creator_address: Address that created the proposal
            tx_hash: Transaction hash of creation
            status: Proposal status (pending, approved, rejected, expired)
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO proposals
                    (id, question_hash, ipfs_cid, question_text, decision_type,
                     context, required_hat_id, deadline, creator_address, tx_hash, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        proposal_id,
                        question_hash,
                        ipfs_cid,
                        question_text,
                        decision_type,
                        json.dumps(context) if context else None,
                        required_hat_id,
                        deadline,
                        creator_address,
                        tx_hash,
                        status,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()

    def update_proposal_status(
        self,
        proposal_id: int,
        status: str,
        yes_votes: int = 0,
        no_votes: int = 0,
    ) -> None:
        """Update proposal status and vote counts.

        Args:
            proposal_id: ID of the proposal
            status: New status (pending, approved, rejected, expired)
            yes_votes: Number of yes votes
            no_votes: Number of no votes
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE proposals
                    SET status = ?, yes_votes = ?, no_votes = ?
                    WHERE id = ?
                """,
                    (status, yes_votes, no_votes, proposal_id),
                )
                conn.commit()

    def record_vote(
        self,
        proposal_id: int,
        voter_address: str,
        support: bool,
        signature: Optional[str] = None,
        tx_hash: Optional[str] = None,
    ) -> None:
        """Record a vote in the database.

        Args:
            proposal_id: ID of the proposal
            voter_address: Address of the voter
            support: True for yes, False for no
            signature: EIP-712 signature
            tx_hash: Transaction hash if on-chain
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO votes
                    (proposal_id, voter_address, support, signature, tx_hash, voted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        proposal_id,
                        voter_address.lower(),
                        support,
                        signature,
                        tx_hash,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()

    def get_proposal(self, proposal_id: int) -> Optional[Dict[str, Any]]:
        """Get a proposal by ID.

        Args:
            proposal_id: ID of the proposal

        Returns:
            Proposal dictionary or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
            row = cursor.fetchone()
            if not row:
                return None

            proposal = dict(row)
            if proposal.get("context"):
                proposal["context"] = json.loads(proposal["context"])
            return proposal

    def get_proposal_by_hash(self, question_hash: str) -> Optional[Dict[str, Any]]:
        """Get a proposal by question hash.

        Args:
            question_hash: Hash of the question

        Returns:
            Proposal dictionary or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM proposals WHERE question_hash = ?", (question_hash,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            proposal = dict(row)
            if proposal.get("context"):
                proposal["context"] = json.loads(proposal["context"])
            return proposal

    def get_proposal_history(
        self, limit: int = 50, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get historical proposals.

        Args:
            limit: Maximum number of proposals to return
            status: Optional status filter

        Returns:
            List of proposal dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    """
                    SELECT * FROM proposals
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (status, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM proposals
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            proposals = []
            for row in cursor.fetchall():
                proposal = dict(row)
                if proposal.get("context"):
                    proposal["context"] = json.loads(proposal["context"])
                proposals.append(proposal)

            return proposals

    def get_votes_for_proposal(self, proposal_id: int) -> List[Dict[str, Any]]:
        """Get all votes for a proposal.

        Args:
            proposal_id: ID of the proposal

        Returns:
            List of vote dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM votes
                WHERE proposal_id = ?
                ORDER BY voted_at DESC
            """,
                (proposal_id,),
            )

            return [dict(row) for row in cursor.fetchall()]

    def get_voter_history(
        self, voter_address: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get voting history for a specific address.

        Args:
            voter_address: Ethereum address
            limit: Maximum number of votes to return

        Returns:
            List of vote dictionaries with proposal info
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.*, p.question_text, p.decision_type, p.status as proposal_status
                FROM votes v
                JOIN proposals p ON v.proposal_id = p.id
                WHERE v.voter_address = ?
                ORDER BY v.voted_at DESC
                LIMIT ?
            """,
                (voter_address.lower(), limit),
            )

            return [dict(row) for row in cursor.fetchall()]

    def get_proposal_cid(self, proposal_id: int) -> Optional[str]:
        """Get the IPFS CID for a proposal.

        Args:
            proposal_id: ID of the proposal

        Returns:
            IPFS CID or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ipfs_cid FROM proposals WHERE id = ?", (proposal_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None