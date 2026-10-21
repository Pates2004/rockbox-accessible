"""Pure exception/report guards; compiler and process execution are mocked."""

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

import test_accessibility_lists as lists
import test_accessibility_service_group as groups

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]


class AccessibilityHarnessReportTests(unittest.TestCase):
    def test_list_timeout_is_never_a_successful_negative_control(self):
        subject = lists.AccessibilityListTests
        for expected_failure in (False, True):
            records = []
            error = subprocess.TimeoutExpired(["unexecuted-guard"], 15)
            with self.subTest(expected_failure=expected_failure), \
                 mock.patch.object(subject, "results", records, create=True), \
                 mock.patch.object(lists.subprocess, "run", side_effect=error), \
                 self.assertRaises(subprocess.TimeoutExpired):
                subject.run_case(Path("unexecuted-guard"), "guard", fails=expected_failure)
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0]["passed"])
            self.assertEqual(records[0]["kind"], "run-exception")

    def test_group_timeout_is_never_a_successful_negative_control(self):
        area = project_materials_root(ROOT) / "accessibility-harness-report-tests" / uuid.uuid4().hex
        area.mkdir(parents=True, exist_ok=False)
        subject = groups.AccessibilityServiceGroupTests
        for expected_failure in (False, True):
            records = []
            with self.subTest(expected_failure=expected_failure), \
                 mock.patch.object(subject, "area", area, create=True), \
                 mock.patch.object(subject, "compiler", ["unexecuted-guard"], create=True), \
                 mock.patch.object(subject, "results", records, create=True), \
                 mock.patch.object(groups.subprocess, "run", side_effect=[
                     SimpleNamespace(returncode=0, stdout="", stderr=""),
                     subprocess.TimeoutExpired(["unexecuted-guard"], 15)]), \
                 self.assertRaises(subprocess.TimeoutExpired):
                subject.run_source("mock-" + str(expected_failure), "int main(void) { return 0; }\n",
                                   failure=expected_failure)
            self.assertEqual(len(records), 2)
            self.assertTrue(records[0]["passed"])
            self.assertFalse(records[1]["passed"])
            self.assertEqual(records[1]["kind"], "run-exception")

    def test_nonzero_crash_or_missing_runtime_is_not_a_causal_assertion(self):
        subject = lists.AccessibilityListTests
        for code in (1, 77, 101, 3221225477, 3221225781):
            records = []
            with self.subTest(exit_code=code), \
                 mock.patch.object(subject, "results", records, create=True), \
                 mock.patch.object(lists.subprocess, "run", return_value=SimpleNamespace(
                     returncode=code, stdout="", stderr="unrelated failure")), \
                 self.assertRaises(AssertionError):
                subject.run_case(Path("unexecuted-guard"), "guard", fails=True)
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0]["passed"])

    def test_unittest_errors_assertions_and_subtests_reach_reports(self):
        for subject, method in ((lists.AccessibilityListTests, "test_settings_use_existing_wrap_and_distinct_feedback_option"),
                                (groups.AccessibilityServiceGroupTests, "test_preferences_and_menu_have_one_group_and_keep_individual_actions")):
            for category in ("errors", "failures"):
                for subtest in (False, True):
                    case = subject(method)
                    result = unittest.TestResult()
                    owner = SimpleNamespace(test_case=case) if subtest else case
                    getattr(result, category).append((owner, "synthetic failure, not a product execution"))
                    case._outcome = SimpleNamespace(result=result)
                    records = []
                    with self.subTest(subject=subject.__name__, category=category, subtest=subtest), \
                         mock.patch.object(subject, "case_results", records, create=True):
                        case.tearDown()
                    self.assertEqual(len(records), 1)
                    self.assertFalse(records[0]["passed"])
                    self.assertTrue(records[0]["failures"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
