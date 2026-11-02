"""Regression tests for targeted province/vehicle runs; no network/database access."""
import unittest
from anc_collector import ANCCollector, PROVINCES, VEHICLES, select_target_scope


class TargetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.targets = list(ANCCollector.targets())

    def test_first_three(self):
        selected = select_target_scope(self.targets, limit=3)
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected[0][1], "สุโขทัย")

    def test_dealer_city_2022(self):
        selected = select_target_scope(self.targets, target_index=11)
        self.assertEqual(len(selected), 1)
        _, province, vehicle = selected[0]
        self.assertEqual(province, "สุโขทัย")
        self.assertEqual((vehicle.brand, vehicle.model, vehicle.year),
                         ("HONDA", "CITY", 2022))

    def test_invalid_index_or_conflict(self):
        for index in (0, len(self.targets) + 1):
            with self.assertRaises(ValueError):
                select_target_scope(self.targets, target_index=index)
        with self.assertRaises(ValueError):
            select_target_scope(self.targets, limit=3, target_index=11)


if __name__ == "__main__":
    unittest.main()
