import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigurationTests(unittest.TestCase):
    def test_dashboard_environment_filter(self):
        dashboard = load("build_dashboard").dashboard()
        for panel in dashboard["panels"]:
            for target in panel["targets"]:
                self.assertIn('environment=~"$environment"', target["expr"])

    def test_dashboard_ids_unique(self):
        panels = load("build_dashboard").dashboard()["panels"]
        self.assertEqual(len(panels), len({panel["id"] for panel in panels}))

    def test_manager_summary_precedes_smaller_technical_cards(self):
        dashboard = load("build_dashboard").dashboard(cloud=True)
        panels = {item["title"]: item for item in dashboard["panels"]}
        for title in ("Customer access", "QC processing health", "Monitoring coverage"):
            self.assertEqual(panels[title]["gridPos"], {"x": panels[title]["gridPos"]["x"], "y": 1, "w": 4 if title == "Monitoring coverage" else 8, "h": 5})
            self.assertTrue(panels[title]["targets"][0]["instant"])
            self.assertEqual(panels[title]["fieldConfig"]["defaults"]["noValue"], "Not reporting")
        self.assertGreater(panels["TLS expiry (days)"]["gridPos"]["y"], 35)
        self.assertEqual(panels["TLS expiry (days)"]["gridPos"]["w"], 6)
        self.assertEqual(dashboard["refresh"], "1m")
        self.assertNotIn("Gemini", " ".join(panels))

    def test_panels_do_not_overlap(self):
        for cloud in (False, True):
            panels = load("build_dashboard").dashboard(cloud=cloud)["panels"]
            for i, panel in enumerate(panels):
                a = panel["gridPos"]
                self.assertLessEqual(a["x"] + a["w"], 24)
                for other in panels[i + 1:]:
                    b = other["gridPos"]
                    overlap = a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]
                    self.assertFalse(overlap, (panel["title"], other["title"]))

    def test_zero_counts_require_fresh_reporting_and_health_checks_expected_targets(self):
        panels = {p["title"]: p for p in load("build_dashboard").dashboard(cloud=True)["panels"]}
        for title in ("Reviews completed", "Reviewed DOCX generated", "Processing attempts failed", "API server errors"):
            expression = panels[title]["targets"][0]["expr"]
            self.assertIn("timestamp(up{", expression)
            self.assertIn("== 1", expression)
            self.assertNotIn("vector(0)", expression)
        self.assertIn("== bool 2", panels["Customer access"]["targets"][0]["expr"])
        self.assertIn("== bool 3", panels["QC processing health"]["targets"][0]["expr"])
        self.assertIn("== bool 4", panels["Monitoring coverage"]["targets"][0]["expr"])

    def test_ai_series_identify_actual_provider_and_hide_preinitialized_zeroes(self):
        panels = {p["title"]: p for p in load("build_dashboard").dashboard(cloud=True)["panels"]}
        for title in ("AI provider calls / hour", "AI reported tokens / hour"):
            target = panels[title]["targets"][0]
            self.assertIn("provider", target["expr"])
            self.assertTrue(target["expr"].endswith("> 0"))
            self.assertIn("{{provider}}", target["legendFormat"])

    def test_email_recipients_match_live_free_plan_decision(self):
        contact = json.loads((ROOT / "grafana/cloud/email.json").read_text())
        test = json.loads((ROOT / "grafana/cloud/email-test.json").read_text())
        self.assertEqual(contact["settings"], test["integration"]["settings"])
        self.assertEqual(contact["settings"]["addresses"].split(";"), ["saikamal@replicantsys.com", "siddharth@replicantsys.com"])
        self.assertFalse(contact["disableResolveMessage"])

    def test_live_alert_list_is_scoped_to_qc_and_includes_error_states(self):
        panel = next(p for p in load("build_dashboard").dashboard(cloud=True)["panels"] if p["type"] == "alertlist")
        self.assertEqual(panel["options"]["folder"]["uid"], "replisense-qc")
        self.assertIn('observability="replisense-qc"', panel["options"]["alertInstanceLabelFilter"])
        self.assertTrue(panel["options"]["stateFilter"]["error"])
        self.assertTrue(panel["options"]["stateFilter"]["noData"])

    def test_latency_panels_require_measured_observations(self):
        panels = {p["title"]: p for p in load("build_dashboard").dashboard(cloud=True)["panels"]}
        for title in ("Response time · 95th percentile",):
            expression = panels[title]["targets"][0]["expr"]
            self.assertIn("_seconds_count", expression)
            self.assertIn("and on(", expression)
            self.assertIn("> 0", expression)

    def test_story_panels_reuse_real_metrics_without_new_collection(self):
        panels = {p["title"]: p for p in load("build_dashboard").dashboard(cloud=True)["panels"]}
        self.assertEqual(panels["Availability history"]["type"], "state-timeline")
        self.assertFalse(panels["Availability history"]["fieldConfig"]["defaults"]["custom"]["spanNulls"])
        heatmap = panels["Review speed distribution"]
        self.assertEqual(heatmap["type"], "heatmap")
        self.assertFalse(heatmap["options"]["calculate"])
        self.assertIn("replisense_worker_job_duration_seconds_bucket", heatmap["targets"][0]["expr"])
        self.assertIn('le!="+Inf"', heatmap["targets"][0]["expr"])
        self.assertIn("timestamp(up{", panels["Telemetry freshness"]["targets"][0]["expr"])
        graph = panels["QC dependency overview"]
        self.assertEqual(graph["type"], "nodeGraph")
        self.assertEqual([t["refId"] for t in graph["targets"]], ["nodes", "edges"])
        self.assertIn("Unknown", graph["targets"][0]["expr"])
        self.assertIn("NOT request traces", graph["description"])
        self.assertIn("environment", graph["targets"][1]["expr"])

    def test_deployment_annotations_are_cloud_scoped(self):
        self.assertEqual(load("build_dashboard").dashboard()["annotations"]["list"], [])
        annotation = load("build_dashboard").dashboard(cloud=True)["annotations"]["list"][0]
        self.assertEqual(annotation["target"]["tags"], ["replisense", "qc", "deployment"])
        self.assertFalse(annotation["target"]["matchAny"])

    def test_cloud_alerts_are_scoped_and_bounded(self):
        rules = load("build_cloud_alerts").rules()
        self.assertEqual(len(rules), 8)
        self.assertEqual(len({rule["uid"] for rule in rules}), 8)
        for rule in rules:
            self.assertEqual(rule["labels"]["environment"], "qc")
            self.assertEqual(rule["labels"]["observability"], "replisense-qc")
            self.assertEqual(rule["folderUID"], "replisense-qc")
            self.assertIn('environment="qc"', rule["data"][0]["model"]["expr"])

    def test_collector_has_no_public_ports_or_docker_socket(self):
        compose = (ROOT / "alloy/compose.yaml").read_text()
        self.assertNotIn("ports:", compose)
        self.assertNotIn("docker.sock", compose)
        self.assertIn("/proc/meminfo:/host/proc/meminfo:ro", compose)
        self.assertIn('user: "0:0"', compose)
        self.assertIn('cap_drop: [ALL]', compose)
        self.assertIn('no-new-privileges:true', compose)

    def test_public_probes_use_routable_ipv4(self):
        config = (ROOT / "alloy/blackbox.yml").read_text()
        self.assertEqual(config.count("preferred_ip_protocol: ip4"), 2)

    def test_cloud_dashboard_certificate_health(self):
        dashboard = load("build_dashboard").dashboard(cloud=True)
        self.assertEqual(dashboard["templating"]["list"][0]["current"]["value"], "qc")
        panel = next(item for item in dashboard["panels"] if item["title"] == "TLS expiry (days)")
        defaults = panel["fieldConfig"]["defaults"]
        self.assertEqual(defaults["unit"], "suffix: days")
        self.assertEqual(defaults["thresholds"]["steps"][-1], {"color": "green", "value": 30})

    def test_external_logs_are_reconstructed_not_forwarded_raw(self):
        config = (ROOT / "alloy/config.alloy").read_text()
        self.assertIn('source = "safe_line"', config)
        self.assertIn('stage.match', config)
        self.assertNotIn("/var/lib/docker", config)

    def test_email_uses_secret_file_and_tls(self):
        result = load("configure_email").config("smtp.example.com:587", "alerts@example.com", "oncall@example.com", "user")
        self.assertTrue(result["global"]["smtp_require_tls"])
        self.assertNotIn("smtp_auth_password", result["global"])
        self.assertEqual(result["global"]["smtp_auth_password_file"], "/run/secrets/smtp_password")
        self.assertTrue(result["receivers"][1]["email_configs"][0]["send_resolved"])

    def test_local_and_heartbeat_do_not_email(self):
        result = load("configure_email").config("smtp.example.com:587", "a", "b", "c")
        self.assertEqual([route["receiver"] for route in result["route"]["routes"]], ["disabled", "disabled"])

    def test_qc_off_hours_mute_uses_ist_operating_window(self):
        config = (ROOT / "scripts/configure_cloud_alerts.py").read_text()
        self.assertIn('MUTE_NAME = "replisense-qc-off-hours"', config)
        self.assertIn('{"start_time": "00:00", "end_time": "10:00"}', config)
        self.assertIn('{"start_time": "18:00", "end_time": "24:00"}', config)
        self.assertIn('"location": "Asia/Kolkata"', config)
        self.assertIn('"mute_time_intervals": [MUTE_NAME]', config)


if __name__ == "__main__":
    unittest.main()
