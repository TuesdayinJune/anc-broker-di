"""User-approved ANCBroker scope and conservative vehicle-screening rules.

No database/network side effects. 'cc' in the website submodel label is
used as a *litre class*, never as a verified displacement in cubic centimetres.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class TargetSpec:
    brand: str
    model: str
    year: int
    repair_type: str
    target_sum_insured: int
    underwriting_code: int = 110


TARGET_SPECS: tuple[TargetSpec, ...] = (
    TargetSpec('HONDA', 'CITY', 2020, 'ซ่อมอู่', 390000),
    TargetSpec('MAZDA', '2', 2019, 'ซ่อมอู่', 310000),
    TargetSpec('TOYOTA', 'YARIS', 2019, 'ซ่อมอู่', 300000),
    TargetSpec('HONDA', 'CIVIC', 2019, 'ซ่อมอู่', 500000),
    TargetSpec('HONDA', 'JAZZ', 2018, 'ซ่อมอู่', 340000),
    TargetSpec('TOYOTA', 'VIOS', 2013, 'ซ่อมอู่', 191000),
    TargetSpec('TOYOTA', 'C-HR', 2019, 'ซ่อมอู่', 560000),
    TargetSpec('NISSAN', 'ALMERA', 2020, 'ซ่อมอู่', 340000),
    TargetSpec('HONDA', 'HR-V', 2018, 'ซ่อมอู่', 470000),
    TargetSpec('ISUZU', 'D-MAX', 2020, 'ซ่อมอู่', 510000),
    TargetSpec('HONDA', 'CITY', 2022, 'ซ่อมห้าง', 470000),
    TargetSpec('TOYOTA', 'YARIS', 2023, 'ซ่อมห้าง', 460000),
    TargetSpec('HONDA', 'HR-V', 2023, 'ซ่อมห้าง', 800000),
    TargetSpec('TOYOTA', 'YARIS CROSS', 2024, 'ซ่อมห้าง', 710000),
    TargetSpec('MAZDA', '2', 2022, 'ซ่อมห้าง', 400000),
    TargetSpec('HONDA', 'CIVIC', 2023, 'ซ่อมห้าง', 860000),
    TargetSpec('TOYOTA', 'COROLLA CROSS', 2022, 'ซ่อมห้าง', 740000),
    TargetSpec('MAZDA', 'CX-30', 2022, 'ซ่อมห้าง', 740000),
    TargetSpec('MAZDA', 'CX-3', 2022, 'ซ่อมห้าง', 530000),
    TargetSpec('MITSUBISHI', 'XFORCE', 2025, 'ซ่อมห้าง', 910000),
)
SPEC_BY_KEY = {(s.brand, s.model, s.year): s for s in TARGET_SPECS}
assert len(SPEC_BY_KEY) == len(TARGET_SPECS) == 20

# Known engine *families* from manufacturers, not proof every website/year
# variant corresponds to that engine. Refer to these sources when reviewing.
DOCUMENTED_CC: dict[tuple[str, str, int, int], tuple[int, str]] = {
    ('MAZDA', 'CX-30', 2022, 1502): (1998, 'https://www.mazda.co.th/en/cars/mazda-cx30-essential/spec'),
    ('MAZDA', 'CX-3', 2022, 814): (1998, 'https://www.mazda.co.th/cars/221546/spec'),
    ('HONDA', 'CIVIC', 2023, 2585): (1993, 'https://www.honda.co.th/civic/specification'),
}


@dataclass(frozen=True)
class Screening:
    action: str  # COLLECT, REVIEW, EXCLUDE
    reason: str
    actual_cc: int | None = None
    cc_source_url: str = ''


def spec_for(vehicle) -> TargetSpec:
    return SPEC_BY_KEY[(vehicle.brand, vehicle.model, int(vehicle.year))]


def assess_variant(vehicle, entry) -> Screening:
    """Never interpret a catalog entry as proof of trim/year or code 110."""
    spec = spec_for(vehicle)
    submodel = str(entry.submodel or '').upper()
    if spec.brand == 'TOYOTA' and spec.model == 'YARIS' and 'YARIS ATIV' in submodel:
        return Screening('EXCLUDE', 'YARIS_ATIV_IS_NOT_REQUESTED_YARIS')

    key = (spec.brand, spec.model, spec.year, int(entry.car_id))
    documented = DOCUMENTED_CC.get(key)
    if documented:
        cc, source = documented
        if cc >= 2000:
            return Screening('EXCLUDE', 'DOCUMENTED_CC_AT_LEAST_2000', cc, source)
        return Screening('COLLECT', 'DOCUMENTED_CC_LT_2000;VERIFY_TRIM_YEAR_AND_CODE110', cc, source)

    label = re.search(r'(?<![\d.])(\d+(?:\.\d+)?)\s*cc\b', submodel, re.I)
    if not label:
        return Screening('REVIEW', 'ENGINE_DISPLACEMENT_NOT_SHOWN')

    litres = float(label.group(1))
    if litres > 2.0:
        return Screening('EXCLUDE', 'ENGINE_LABEL_ABOVE_2_LITRES')
    if litres == 2.0:
        return Screening('REVIEW', '2L_ENGINE_REQUIRES_ACTUAL_CC_BEFORE_COLLECTION')
    return Screening('COLLECT', 'NOMINAL_LT_2L;VERIFY_ACTUAL_CC_TRIM_YEAR_AND_CODE110')


def write_scope_reports(vehicles: Iterable, catalog, folder: Path = Path('.')) -> tuple[Path, Path]:
    """Write reviewable target/trim audit CSVs. Never changes website or DB."""
    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / 'anc_target_requirements.csv'
    variant_path = folder / 'anc_variant_screening.csv'
    with target_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'brand', 'model', 'year', 'repair_type', 'target_sum_insured', 'underwriting_code'])
        writer.writeheader()
        for s in TARGET_SPECS:
            writer.writerow(vars(s))

    with variant_path.open('w', encoding='utf-8-sig', newline='') as f:
        fieldnames = ['brand', 'model', 'year', 'repair_type', 'target_sum_insured',
                      'underwriting_code', 'submodel', 'car_id', 'reference_year',
                      'action', 'reason', 'documented_cc', 'cc_source_url',
                      'reference_url', 'year_trim_verified']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for v in vehicles:
            spec = spec_for(v)
            for e in catalog.candidates(v):
                a = assess_variant(v, e)
                writer.writerow({
                    'brand': spec.brand, 'model': spec.model, 'year': spec.year,
                    'repair_type': spec.repair_type, 'target_sum_insured': spec.target_sum_insured,
                    'underwriting_code': spec.underwriting_code, 'submodel': e.submodel,
                    'car_id': e.car_id, 'reference_year': e.reference_year,
                    'action': a.action, 'reason': a.reason,
                    'documented_cc': a.actual_cc if a.actual_cc is not None else '',
                    'cc_source_url': a.cc_source_url, 'reference_url': e.reference_url,
                    'year_trim_verified': 'NO',
                })
    return target_path, variant_path
