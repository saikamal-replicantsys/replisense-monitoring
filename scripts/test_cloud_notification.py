"""Controlled setup-only alert. No application outage, document or LLM request.

--phase fire creates an isolated synthetic rule; --phase resolve makes it healthy.
--phase pause disables the test rule after verification. Do not use it for live QC.
"""
import argparse
import copy
import json
import subprocess
from build_cloud_alerts import rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcx", default="gcx")
    parser.add_argument("--phase", choices=["fire", "resolve", "pause"], required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    rule = copy.deepcopy(rules()[0])
    rule.update(uid="replisense-qc-notification-test", title="QC notification delivery test", **{"for": "0s"})
    rule["labels"].update(severity="info", setup_test="true")
    rule["annotations"] = {"summary": "QC monitoring setup test", "description": "Controlled notification-routing test. No real outage or client evaluation is involved."}
    rule["data"][0]["model"]["expr"] = "vector(1)" if args.phase == "fire" else "vector(0)"
    rule["data"][2]["model"]["conditions"][0]["evaluator"] = {"type": "gt", "params": [0]}
    rule["isPaused"] = args.phase == "pause"
    if not args.execute:
        print(json.dumps(rule, indent=2))
        return
    existing = subprocess.run([args.gcx, "--context", "replisense", "api", "/api/v1/provisioning/alert-rules", "-o", "json"], check=True, encoding="utf-8", capture_output=True)
    prior = next((item for item in json.loads(existing.stdout) if item["uid"] == rule["uid"]), None)
    if prior and (prior.get("labels", {}).get("setup_test") != "true" or prior["folderUID"] != "replisense-qc"):
        raise RuntimeError("UID is not our owned setup-test rule")
    path = "/api/v1/provisioning/alert-rules" + ("/" + rule["uid"] if prior else "")
    subprocess.run([args.gcx, "--context", "replisense", "api", path, "-X", "PUT" if prior else "POST", "-d", "@-"],
                   input=json.dumps(rule), text=True, encoding="utf-8", check=True, stdout=subprocess.DEVNULL)
    print("Synthetic QC notification test phase:", args.phase)


if __name__ == "__main__":
    main()
