import importlib.util
import unittest
from pathlib import Path


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/build_writer_observability.py"
    spec = importlib.util.spec_from_file_location("writer_observability", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class WriterObservabilityTests(unittest.TestCase):
    def test_dashboard_is_environment_scoped_and_does_not_hide_missing_data(self):
        panels = module().dashboard()["panels"]
        self.assertEqual(len(panels), len({panel["id"] for panel in panels}))
        for panel in panels:
            self.assertIn('environment=~"$environment"', panel["targets"][0]["expr"])
            self.assertNotIn("or vector(0)", panel["targets"][0]["expr"])
            self.assertEqual(panel["fieldConfig"]["defaults"]["noValue"], "Not reporting")

    def test_alerts_are_writer_scoped_and_do_not_enable_qc_workers(self):
        rules = module().alert_rules()["groups"][0]["rules"]
        self.assertEqual(len(rules), 6)
        for rule in rules:
            self.assertEqual(rule["labels"]["module"], "writer")
            self.assertIn("writer", rule["expr"])
            self.assertNotIn('environment="qc"', rule["expr"])


if __name__ == "__main__":
    unittest.main()
