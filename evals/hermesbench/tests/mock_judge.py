"""Minimal OpenAI-compatible endpoint returning a fixed judge verdict (for e2e tests)."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        verdict = {"scores": {"format_compliance": 1.0, "subject_line_quality": 0.5, "body_quality": 0.0, "accuracy_and_completeness": 1.0}, "total": 0.625, "notes": "mock"}
        body = json.dumps({"choices": [{"message": {"content": "```json\n" + json.dumps(verdict) + "\n```"}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a):
        pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
