"""Offline tests for read-only ANC data-quality audit."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from anc_data_quality import analyze, write_report


class QualityTests(unittest.TestCase):
    def test_shared_detail_and_mismatch(self):
        url = "https://www.ancbroker.com/plan"
        rows = [
            {"source_url": url, "premium": "11500", "actual_sum_insured": "400000",
             "detail_status": "DONE", "validation_status": "REVIEW_REQUIRED",
             "insurer": "MSIG", "package_name": "Test",
             "raw_detail": json.dumps({"premium": "8000", "coverage_own_damage": "100000"})},
            {"source_url": url, "premium": "8000", "actual_sum_insured": "100000",
             "detail_status": "DONE", "validation_status": "DETAIL_VERIFIED",
             "insurer": "MSIG", "package_name": "Test",
             "raw_detail": json.dumps({"premium": "8000", "coverage_own_damage": "100000"})},
        ]
        results = analyze(rows)
        self.assertEqual(results[0]["premium_abs_diff"], "3500")
        self.assertNotIn("DETAIL_OWN_DAMAGE_DIFF_FROM_SUM", results[0]["review_flags"])
        self.assertEqual(results[0]["detail_own_damage_observed"], "100000")
        self.assertIn("SHARED_DETAIL_URL_MULTI_SUM", results[1]["information_flags"])
        self.assertEqual(results[0]["price_context_status"], "SHARED_URL_PLAN_REFERENCE")
        self.assertEqual(results[0]["needs_review"], "NO")
        self.assertEqual(rows[0]["premium"], "11500")

    def test_unavailable_and_rounding(self):
        rows = [
            {"source_url": "/x", "premium": "1000.00", "actual_sum_insured": "100000",
             "detail_status": "DETAIL_UNAVAILABLE", "raw_detail": "", "insurer": ""},
            {"source_url": "/y", "premium": "1000.30", "actual_sum_insured": "100000",
             "detail_status": "DONE", "validation_status": "DETAIL_VERIFIED",
             "insurer": "Test", "raw_detail": json.dumps({"premium": "1000"})},
        ]
        results = analyze(rows)
        self.assertEqual(results[0]["needs_review"], "YES")
        self.assertEqual(results[1]["needs_review"], "NO")

    def test_target_sum_gap(self):
        offer = {"brand":"HONDA", "model":"CITY", "vehicle_year":"2020", "repair_type":"ซ่อมอู่",
                 "actual_sum_insured":"400000", "premium":"11500", "detail_status":"DONE",
                 "validation_status":"DETAIL_VERIFIED", "insurer":"MSIG", "source_url":"/x"}
        result = analyze([offer])[0]
        self.assertEqual(result["target_sum_insured"], "390000")
        self.assertEqual(result["target_sum_gap_thb"], "10000")
        self.assertEqual(result["target_sum_gap_pct"], "2.56")
        self.assertEqual(result["sum_match_status"], "ALTERNATIVE")
        self.assertEqual(result["needs_review"], "NO")

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["source_url", "premium", "actual_sum_insured", "detail_status", "raw_detail", "insurer"])
                w.writeheader()
                w.writerow({"source_url": "/x", "premium": "1000", "actual_sum_insured": "100000",
                            "detail_status": "DETAIL_UNAVAILABLE", "raw_detail": "", "insurer": ""})
            paths = write_report(source, Path(d) / "out")
            self.assertTrue(all(p.exists() for p in paths.values()))
            self.assertEqual(sum(1 for _ in paths["review"].open(encoding="utf-8-sig")) - 1, 1)


if __name__ == "__main__":
    unittest.main()
