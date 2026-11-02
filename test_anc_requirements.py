"""Run: python -m unittest -v test_anc_requirements"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from anc_requirements import TARGET_SPECS, assess_variant, spec_for, write_scope_reports


def vehicle(brand, model, year):
    return Obj(brand=brand, model=model, year=year)


def entry(submodel, car_id):
    return Obj(submodel=submodel, car_id=car_id, reference_year=2015,
               reference_url='https://www.ancbroker.com/test')


class RuleTests(unittest.TestCase):
    def test_20_specs_and_repairs(self):
        self.assertEqual(len(TARGET_SPECS), 20)
        self.assertEqual([s.repair_type for s in TARGET_SPECS].count('ซ่อมอู่'), 10)
        self.assertEqual([s.repair_type for s in TARGET_SPECS].count('ซ่อมห้าง'), 10)
        self.assertEqual(spec_for(vehicle('HONDA', 'CITY', 2020)).target_sum_insured, 390000)

    def test_dmax_2_2_excluded(self):
        a = assess_variant(vehicle('ISUZU', 'D-MAX', 2020), entry('D-MAX 2.2cc 4 Door', 2693))
        self.assertEqual(a.action, 'EXCLUDE')

    def test_dmax_1_9_candidate(self):
        a = assess_variant(vehicle('ISUZU', 'D-MAX', 2020), entry('D-MAX 1.9cc 4 Door', 818))
        self.assertEqual(a.action, 'COLLECT')

    def test_2l_unknown_requires_review(self):
        a = assess_variant(vehicle('HONDA', 'CIVIC', 2019), entry('CIVIC 2.0cc 4 Door', 4))
        self.assertEqual(a.action, 'REVIEW')

    def test_cx30_documented_1998(self):
        a = assess_variant(vehicle('MAZDA', 'CX-30', 2022), entry('CX-30 2.0cc 4 Door', 1502))
        self.assertEqual((a.action, a.actual_cc), ('COLLECT', 1998))

    def test_civic_hybrid_documented_1993(self):
        a = assess_variant(vehicle('HONDA', 'CIVIC', 2023), entry('CIVIC HYBRID 2.0cc 4 Door', 2585))
        self.assertEqual((a.action, a.actual_cc), ('COLLECT', 1993))

    def test_yaris_ativ_is_separate(self):
        a = assess_variant(vehicle('TOYOTA', 'YARIS', 2019), entry('YARIS ATIV 1.2cc 4 Door', 1427))
        self.assertEqual(a.action, 'EXCLUDE')
        cross = assess_variant(vehicle('TOYOTA', 'YARIS CROSS', 2024), entry('YARIS CROSS 1.5cc 5 Door', 2602))
        self.assertEqual(cross.action, 'COLLECT')

    def test_report_files(self):
        v = vehicle('HONDA', 'CITY', 2020)
        catalog = Obj(candidates=lambda _: [entry('CITY 1.5cc 4 Door', 12)])
        with tempfile.TemporaryDirectory() as d:
            a, b = write_scope_reports([v], catalog, Path(d))
            self.assertTrue(a.exists() and b.exists())
            self.assertIn('390000', b.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
