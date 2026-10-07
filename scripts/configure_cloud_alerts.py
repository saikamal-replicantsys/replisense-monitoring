"""Review/apply only QC-owned rules and one scoped email notification route.

Preserves other teams' policies and rules. Backs up previous configuration in
ignored artifacts/. Checks telemetry before unpausing live rules. No paid upgrade.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from build_cloud_alerts import rules

ROOT = Path(__file__).resolve().parents[1]


def cli(executable, *args, payload=None):
    result = subprocess.run([executable, "--context", "replisense", *args], text=True, encoding="utf-8", capture_output=True,
                            input=json.dumps(payload) if payload is not None else None)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    if not result.stdout.strip():
        return None
    if args[:3] == ("alert", "notification-policies", "set"):
        return result.stdout # This CLI mutation prints a status message, not JSON.
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcx", default="gcx")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--paused", action="store_true", help="Install rules paused until collector is verified")
    args = parser.parse_args()
    existing = cli(args.gcx, "api", "/api/v1/provisioning/alert-rules", "-o", "json")
    policy = cli(args.gcx, "alert", "notification-policies", "get", "-o", "json")
    policy_baseline = json.dumps(policy, sort_keys=True)
    current = {item["uid"]: item for item in existing}
    candidate = rules()
    for rule in candidate:
        prior = current.get(rule["uid"])
        if prior and (prior["folderUID"] != "replisense-qc" or prior.get("labels", {}).get("observability") != "replisense-qc"):
            raise RuntimeError("Refusing to overwrite an unrelated alert rule")
        rule["isPaused"] = args.paused
    routes = policy.setdefault("routes", [])
    matcher = [["observability", "=", "replisense-qc"]]
    owned = [route for route in routes if route.get("object_matchers") == matcher]
    if len(owned) > 1:
        raise RuntimeError("Duplicate QC notification routes; review manually")
    route = {"receiver": "RepliSense QC email", "object_matchers": matcher,
             "group_by": ["environment", "severity"], "group_wait": "30s", "group_interval": "10m", "repeat_interval": "4h", "continue": False}
    if owned:
        routes[routes.index(owned[0])] = route
    else:
        routes.insert(0, route)
    if not args.execute:
        print(json.dumps({"rules": candidate, "policy": policy}, indent=2))
        return
    if not args.paused:
        data = cli(args.gcx, "datasources", "prometheus", "query", "-d", "grafanacloud-prom",
                   'sum(up{environment="qc",job=~"replisense-(node-api|qc-worker|python-gateway)"})', "-o", "json")
        # Do not silently activate outage alerts before the collector is live.
        samples = data.get("data", {}).get("result", [])
        if len(samples) != 1 or float(samples[0]["value"][1]) != 3:
            raise RuntimeError("Verify all three private scrape targets are up before enabling rules")
    backup = ROOT / "artifacts" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup.mkdir(parents=True)
    (backup / "alert-rules.json").write_text(json.dumps(existing, indent=2))
    # Read live policy again for the exact untouched rollback copy.
    previous_policy = cli(args.gcx, "alert", "notification-policies", "get", "-o", "json")
    if json.dumps(previous_policy, sort_keys=True) != policy_baseline:
        raise RuntimeError("Notification policy changed concurrently; refusing to overwrite it. Review and retry.")
    (backup / "notification-policy.json").write_text(json.dumps(previous_policy, indent=2))
    for rule in candidate:
        path = "/api/v1/provisioning/alert-rules"
        method = "POST"
        if rule["uid"] in current:
            path += "/" + rule["uid"]
            method = "PUT"
        cli(args.gcx, "api", path, "-X", method, "-d", "@-", "-o", "json", payload=rule)
    fresh = cli(args.gcx, "alert", "notification-policies", "get", "-o", "json")
    if json.dumps(fresh, sort_keys=True) != policy_baseline:
        raise RuntimeError("Notification policy changed during rule provisioning; leave it untouched and review.")
    cli(args.gcx, "alert", "notification-policies", "set", "-f", "-", "--force", "-o", "json", payload=policy)
    saved = cli(args.gcx, "api", "/api/v1/provisioning/alert-rules", "-o", "json")
    print("QC rules saved:", len([item for item in saved if item.get("labels", {}).get("observability") == "replisense-qc"]))
    print("Previous configuration backed up at", backup)


if __name__ == "__main__":
    main()
