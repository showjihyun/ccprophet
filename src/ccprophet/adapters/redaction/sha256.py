from __future__ import annotations

import hashlib


class SHA256Redactor:
    def redact_path(self, path: str) -> str:
        return f"<hash:{hashlib.sha256(path.encode()).hexdigest()[:12]}>"

    def redact_command(self, cmd: str) -> str:
        parts = cmd.split()
        if parts:
            return parts[0]
        return "<empty>"
