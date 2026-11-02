"""Read-only ANCBroker quality audit from Collector CSV; stdlib only.

python anc_data_quality.py --input anc_competitor_insurance_24_provinces.csv --out anc_audit_output
This never reads website or writes to SQLite/MySQL.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from anc_requirements import SPEC_BY_KEY


def decimal_value(value):
    if value is None or str(value).strip().lower() in ('', 'none', 'nan', 'null'):
        return None
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None


def raw_json(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def analyze(rows):
    """Return annotated rows without changing input; never assume sum=own damage."""
    groups = defaultdict(set)
    for row in rows:
        url = (row.get('source_url') or '').strip()
        sum_insured = decimal_value(row.get('actual_sum_insured'))
        if url and sum_insured is not None:
            groups[url].add(sum_insured)

    annotated = []
    for data in rows:
        row = dict(data)
        raw = raw_json(row.get('raw_detail'))
        listing_price = decimal_value(row.get('premium'))
        detail_price = decimal_value(raw.get('premium'))
        listing_sum = decimal_value(row.get('actual_sum_insured'))
        detail_own = decimal_value(raw.get('coverage_own_damage'))
        diff = (abs(listing_price - detail_price)
                if listing_price is not None and detail_price is not None else None)
        status = (row.get('detail_status') or '').upper()
        flags = []
        if status != 'DONE':
            flags.append(status or 'DETAIL_NOT_VERIFIED')
        if diff is not None:
            if diff > 100:
                flags.append('PREMIUM_DIFF_GT_100')
            elif diff > 1:
                flags.append('PREMIUM_DIFF_1_TO_100')
            elif diff > 0:
                flags.append('PRICE_ROUNDING_LT_1')
        url = (row.get('source_url') or '').strip()
        if url and len(groups[url]) > 1:
            flags.append('SHARED_DETAIL_URL_MULTI_SUM')
        if not (row.get('insurer') or '').strip():
            flags.append('INSURER_NAME_MISSING')
        label = (row.get('package_name') or '').lower()
        if any(s in label for s in ('กรุงเทพ', 'กทม.', 'ปริมณฑล', '(bkk)', 'bangkok')):
            flags.append('PACKAGE_LOCATION_REVIEW')
        # Ignore legacy V2 notes that incorrectly equated Own Damage with Sum.
        legacy_notes = set((row.get('validation_notes') or '').split(';'))
        actual_notes = legacy_notes - {'', 'DETAIL_OWN_DAMAGE_DIFFERS_FROM_LISTING_SUM'}
        if status == 'DONE' and actual_notes:
            flags.append('VALIDATION_REVIEW_REQUIRED')
        # Rounding is not by itself a re-collection request.
        review = any(f != 'PRICE_ROUNDING_LT_1' for f in flags)
        spec = SPEC_BY_KEY.get(((row.get('brand') or '').upper(),
                                (row.get('model') or '').upper(),
                                int(row.get('vehicle_year') or 0)))
        target = Decimal(spec.target_sum_insured) if spec else None
        signed_gap = listing_sum - target if listing_sum is not None and target is not None else None
        gap_percent = ((signed_gap / target) * 100).quantize(Decimal('0.01')) if signed_gap is not None and target else None
        row.update({
            'listing_premium': str(listing_price) if listing_price is not None else '',
            'listing_sum_insured': str(listing_sum) if listing_sum is not None else '',
            'target_sum_insured': str(target) if target is not None else '',
            'target_sum_gap_thb': str(signed_gap) if signed_gap is not None else '',
            'target_sum_abs_gap_thb': str(abs(signed_gap)) if signed_gap is not None else '',
            'target_sum_gap_pct': str(gap_percent) if gap_percent is not None else '',
            'sum_match_status': 'NOT_APPLICABLE' if target is None or listing_sum is None else ('EXACT' if signed_gap == 0 else 'ALTERNATIVE'),
            'detail_premium_observed': str(detail_price) if detail_price is not None else '',
            'premium_abs_diff': str(diff) if diff is not None else '',
            'detail_own_damage_observed': str(detail_own) if detail_own is not None else '',
            'shared_detail_url_distinct_sums': len(groups[url]) if url else 0,
            'review_flags': ';'.join(flags),
            'needs_review': 'YES' if review else 'NO',
        })
        annotated.append(row)
    return annotated


def write_report(input_csv, output_dir):
    """Generate all offers, review queue, and summary. Original CSV unchanged."""
    input_csv, output_dir = Path(input_csv), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with input_csv.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        original_fields = list(reader.fieldnames or [])
        rows = analyze(list(reader))
    more = ['listing_premium', 'listing_sum_insured', 'target_sum_insured', 'target_sum_gap_thb',
            'target_sum_abs_gap_thb', 'target_sum_gap_pct', 'sum_match_status',
            'detail_premium_observed', 'premium_abs_diff',
            'detail_own_damage_observed', 'shared_detail_url_distinct_sums',
            'review_flags', 'needs_review']
    fields = original_fields + [f for f in more if f not in original_fields]
    paths = {'all': output_dir / 'anc_audit_all.csv',
             'review': output_dir / 'anc_audit_review_queue.csv',
             'summary': output_dir / 'anc_audit_summary.csv'}
    for kind in ('all', 'review'):
        values = rows if kind == 'all' else [r for r in rows if r['needs_review'] == 'YES']
        with paths[kind].open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(values)
    counters = Counter()
    for row in rows:
        counters['STATUS:' + (row.get('detail_status') or '(blank)')] += 1
        for flag in (row['review_flags'] or '').split(';'):
            if flag:
                counters['FLAG:' + flag] += 1
    with paths['summary'].open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['metric', 'count'])
        writer.writerow(['TOTAL_OFFERS', len(rows)])
        writer.writerow(['REVIEW_QUEUE', sum(r['needs_review'] == 'YES' for r in rows)])
        writer.writerows(sorted(counters.items()))
    return paths


def main(argv=None):
    p = argparse.ArgumentParser(description='Audit ANC Collector CSV without website/DB access')
    p.add_argument('--input', required=True)
    p.add_argument('--out', default='anc_audit_output')
    args = p.parse_args(argv)
    for name, path in write_report(args.input, args.out).items():
        print(f'{name}: {path}')


if __name__ == '__main__':
    main()
