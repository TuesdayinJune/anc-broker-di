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

    def test_target_range(self):
        batch = select_target_scope(self.targets, start_index=21, end_index=40)
        self.assertEqual(len(batch), 20)
        self.assertEqual(batch[0][1], "พะเยา")
        self.assertEqual((batch[0][2].brand, batch[0][2].model, batch[0][2].year),
                         ("HONDA", "CITY", 2020))
        self.assertEqual(batch[-1][1], "พะเยา")

    def test_full_range_and_invalid_ranges(self):
        self.assertEqual(len(select_target_scope(self.targets, start_index=1, end_index=480)), 480)
        for bad in ((0, 20), (21, 20), (1, 481)):
            with self.assertRaises(ValueError):
                select_target_scope(self.targets, start_index=bad[0], end_index=bad[1])
        with self.assertRaises(ValueError):
            select_target_scope(self.targets, limit=20, start_index=21, end_index=40)


if __name__ == "__main__":
    unittest.main()
