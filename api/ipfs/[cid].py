"""Vercel serverless function for fetching IPFS content."""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

IPFS_GATEWAY = os.environ.get("IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Extract CID from path
            path_parts = self.path.split("/")
            cid = path_parts[-1].split("?")[0] if path_parts else None

            if not cid:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing CID"}).encode())
                return

            # Fetch from IPFS gateway
            url = f"{IPFS_GATEWAY}/{cid}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Ralph-Orchestrator/1.0")

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                content_type = response.headers.get("Content-Type", "application/json")

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"IPFS fetch failed: {e.reason}"}).encode())

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
