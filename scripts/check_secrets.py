"""Scan staged Git contents, without printing detected values."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "provider token": r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "private IPv4 address": r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
    "MAC address": r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b",
    "personal Windows path": r"[A-Za-z]:\\(?:Users|My Drive)\\",
}
FORBIDDEN = {"secrets.yaml", "secrets.yml", ".env", "display_settings.json", "options.json"}

def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    findings = []
    count = 0
    for name in filter(None, paths):
        count += 1
        path = Path(name)
        if path.name in FORBIDDEN or path.suffix in {".pem", ".key", ".p12", ".pfx", ".bin", ".zip"}:
            findings.append((name, "forbidden file"))
            continue
        raw = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
        try: text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append((name, "unexpected binary file")); continue
        for label, pattern in CHECKS.items():
            if re.search(pattern, text): findings.append((name, label))
        if path.name == "secrets.example.yaml":
            # The checked-in sample must contain placeholders, never actual values.
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith("#"): continue
                key, _, value = line.partition(":")
                if not value.strip().strip("\"'").startswith("YOUR_"):
                    findings.append((name, "non-placeholder secret example"))
    if not count:
        print("No staged/tracked files to scan. Run git add first.")
        return 1
    for name, label in findings: print(f"FAIL: {name}: {label}")
    if findings: return 1
    print(f"PASS: scanned {count} staged/tracked files; no flagged secrets or private metadata.")
    print("Heuristic checks supplement review; they do not prove all possible secrets are absent.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
