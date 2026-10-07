"""Create ignored SMTP configuration without echoing credentials (stdlib only)."""
import argparse
import getpass
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def config(host, sender, recipient, username):
    return {
        "global": {
            "resolve_timeout": "5m", "smtp_smarthost": host,
            "smtp_from": sender, "smtp_auth_username": username,
            "smtp_auth_password_file": "/run/secrets/smtp_password",
            "smtp_require_tls": True,
        },
        "route": {
            "receiver": "email", "group_by": ["environment", "alertname", "service", "worker", "job"],
            "group_wait": "30s", "group_interval": "5m", "repeat_interval": "4h",
            "routes": [
                {"matchers": ['severity="heartbeat"'], "receiver": "disabled"},
                {"matchers": ['environment="local"'], "receiver": "disabled"},
            ],
        },
        "receivers": [
            {"name": "disabled"},
            {"name": "email", "email_configs": [{"to": recipient, "send_resolved": True}]},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smtp", required=True, help="STARTTLS SMTP endpoint, e.g. host:587")
    parser.add_argument("--sender", required=True)
    parser.add_argument("--recipient", default="saikamal@replicantsys.com")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    if any("\n" in value or "\r" in value for value in vars(args).values()):
        parser.error("Fields must be single-line values")
    if not args.smtp.endswith(":587"):
        parser.error("Use a STARTTLS SMTP endpoint on port 587")
    password = getpass.getpass("SMTP password (not displayed): ")
    if not password or "\n" in password or "\r" in password:
        parser.error("A non-empty single-line password is required")
    secret = ROOT / "secrets/smtp_password"
    output = ROOT / "alertmanager/email.local.yml"
    if secret.exists() or output.exists():
        parser.error("Existing email configuration found; refusing to overwrite credentials")
    secret.parent.mkdir(exist_ok=True)
    secret.write_text(password, encoding="utf-8")
    secret.chmod(0o600)
    output.write_text(json.dumps(config(args.smtp, args.sender, args.recipient, args.username), indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print("Created ignored SMTP config. Set ALERTMANAGER_CONFIG=./alertmanager/email.local.yml and recreate Alertmanager.")
    print("On Windows, restrict secrets directory ACLs to your account. No test email was sent.")


if __name__ == "__main__":
    main()
