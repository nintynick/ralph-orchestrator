"""Vercel serverless function for fetching proposals."""
import json
import os
from http.server import BaseHTTPRequestHandler
from web3 import Web3

# Contract configuration
RPC_URL = os.environ.get("BASE_RPC_URL", "https://base.publicnode.com")
CONTRACT_ADDRESS = os.environ.get(
    "RALPH_PROPOSAL_CONTRACT", "0x5c63baF1501B9c50dA4a9e1A38BeC430a2b3d4Df"
)

# Minimal ABI for reading proposals
PROPOSAL_ABI = [
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
    {
        "inputs": [],
        "name": "proposalCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            w3 = Web3(Web3.HTTPProvider(RPC_URL))
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=PROPOSAL_ABI
            )

            # Get proposal count
            count = contract.functions.proposalCount().call()

            # Fetch recent proposals (last 20)
            proposals = []
            current_time = w3.eth.get_block("latest").timestamp

            start = max(1, count - 19)
            for i in range(start, count + 1):
                try:
                    p = contract.functions.getProposal(i).call()
                    proposal = {
                        "id": p[0],
                        "question": p[1],
                        "requiredHatId": str(p[2]),
                        "deadline": p[3],
                        "yesVotes": p[4],
                        "noVotes": p[5],
                        "executed": p[6],
                        "ipfsCid": p[7],
                        "isActive": p[3] > current_time and not p[6],
                    }
                    proposals.append(proposal)
                except Exception:
                    continue

            # Sort by ID descending (newest first)
            proposals.sort(key=lambda x: x["id"], reverse=True)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"proposals": proposals}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
