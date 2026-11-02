"""Offline SQLite smoke tests. No website requests and no MySQL required.

Run:
 .\.venv\Scripts\python.exe -m unittest -v test_anc_sqlite
"""
from __future__ import annotations
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anc_collector import (
    Database, Package, Vehicle, RECORD_TABLE, TARGET_TABLE,
    BRANCH_TABLE, PACKAGE_TABLE, target_key, branch_key
)
from decimal import Decimal


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "test.sqlite3")
        self.env = patch.dict(os.environ, {"ANC_DB_BACKEND": "sqlite", "ANC_SQLITE_PATH": self.path})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = Database().connect()
        self.db.initialize()
        self.addCleanup(self.db.close)

    def test_tables_created(self):
        rows = self.db.connection.raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r["name"] for r in rows}
        self.assertTrue({RECORD_TABLE, TARGET_TABLE, BRANCH_TABLE, PACKAGE_TABLE} <= names)

    def test_record_and_checkpoint_round_trip(self):
        v = Vehicle("HONDA", "CITY", 2020)
        province = "สุโขทัย"
        bkey = branch_key(province, v, 1473, "ซ่อมอู่")
        p = Package(
            branch_key=bkey, record_key="a"*64,
            source_url="https://www.ancbroker.com/test-detail",
            listing_url="https://www.ancbroker.com/test-list",
            region="ภาคเหนือ", province=province, brand=v.brand, model=v.model,
            submodel="CITY 1.0cc 4 Doors", car_id=1473, vehicle_year=v.year,
            repair_type="ซ่อมอู่", package_id="PK001", insurer_code="CODE1",
            package_name="TEST PACKAGE", premium=Decimal("12000.50"),
            sum_insured=Decimal("390000.00"),
        )
        self.assertEqual(self.db.save_package(p, "PENDING"), "INSERTED")
        self.assertEqual(self.db.get_package_status(p.record_key), "PENDING")
        p.detail_status = "DONE"
        p.coverage_third_party_property = Decimal("1000000.00")
        self.assertEqual(self.db.save_package(p, "DONE"), "UPDATED")
        self.assertEqual(self.db.get_package_status(p.record_key), "DONE")

        self.db.set_target("ภาคเหนือ", province, v, "RUNNING", 3)
        self.db.set_branch(bkey, target_key(province, v), 1473, "ซ่อมอู่",
                           "DONE", "https://www.ancbroker.com/listing", [])
        self.db.set_target("ภาคเหนือ", province, v, "DONE", 3)
        self.assertEqual(self.db.get_branch_status(bkey)["status"], "DONE")
        self.assertEqual(self.db.get_target_status(target_key(province,v))["status"], "DONE")
        self.assertEqual(self.db.stats()["records"], 1)
        self.assertEqual(self.db.stats()["details_done"], 1)
        self.assertEqual(self.db.target_stats()["DONE"], 1)
        self.assertEqual(
            self.db.connection.raw.execute(
                f'SELECT attempts FROM "{PACKAGE_TABLE}" WHERE record_key=?',
                (p.record_key,)
            ).fetchone()["attempts"], 2
        )

        out = Path(self.temp.name) / "offers.csv"
        self.assertEqual(self.db.export_csv(out), 1)
        with out.open(encoding="utf-8-sig", newline="") as f:
            data = list(csv.DictReader(f))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["province"], province)
        self.assertEqual(Decimal(data[0]["premium"]), Decimal("12000.50"))

    def test_no_dangling_server(self):
        self.assertTrue(Path(self.path).exists())
        self.assertEqual(self.db.connection.filename, Path(self.path).resolve())


if __name__ == "__main__":
    unittest.main()
