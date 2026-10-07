#!/usr/bin/env python3
"""Fetch minimal scoped credentials using EC2 IAM. Never print values."""
import json
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Run as root through SSM/systemd")
    os.umask(0o077)
    root = Path("/run/replisense-qc-observability")
    root.mkdir(mode=0o700, exist_ok=True)
    for parameter, filename in (("GRAFANA_CLOUD_TOKEN", "grafana-token"), ("OBSERVABILITY_TOKEN", "observability-token")):
        result = subprocess.run(["aws", "ssm", "get-parameter", "--region", "ap-south-1", "--name", "/replisense/qc/" + parameter,
                                 "--with-decryption", "--output", "json"], check=True, text=True, capture_output=True)
        value = json.loads(result.stdout)["Parameter"]["Value"]
        if not value or "\n" in value or "REPLACE" in value:
            raise RuntimeError("Missing valid telemetry parameter: " + parameter)
        path = root / filename
        path.write_text(value)
        path.chmod(0o600)
    for service in ("node-api", "qc-worker", "python-gateway"):
        directory = Path("/var/log/replisense-ops") / service
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
