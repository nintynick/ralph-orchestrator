"""Vercel serverless function for recording votes."""
import json
import os
from http.server import BaseHTTPRequestHandler
from web3 import Web3

# Contract configuration
RPC_URL = os.environ.get("BASE_RPC_URL", "https://base.publicnode.com")
CONTRACT_ADDRESS = os.environ.get(
    "RALPH_PROPOSAL_CONTRACT", "0x5c63baF1501B9c50dA4a9e1A38BeC430a2b3d4Df"
)

# Minimal ABI for voting
VOTE_ABI = [
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
        "name": "getProposal",
        "outputs": [
            {"name": "id", "type": "uint256"},
            {"name": "question", "type": "string"},
            {"name": "requiredHatId", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "yesVotes", "type": "uint256"},
            {"name": "noVotes", "type": "uint256"},
            {"name": "executed", "type": "bool"},
            {"name": "ipfsCid", "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            proposal_id = data.get("proposalId")
            support = data.get("support")
            voter = data.get("voter")
            tx_hash = data.get("txHash")

            if not all([proposal_id is not None, support is not None, voter]):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Missing required fields"}).encode()
                )
                return

            # For serverless, we just acknowledge the vote
            # The actual vote happens on-chain via the user's wallet
            # This endpoint can be used for analytics/caching

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "message": "Vote recorded",
                        "proposalId": proposal_id,
                        "support": support,
                        "voter": voter,
                        "txHash": tx_hash,
                    }
                ).encode()
            )

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
