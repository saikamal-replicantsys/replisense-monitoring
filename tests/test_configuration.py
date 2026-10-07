import importlib.util
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


if __name__ == "__main__":
    unittest.main()
