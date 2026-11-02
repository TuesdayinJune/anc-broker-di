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
    def detail_group_key(row):
        # Same URL on another vehicle/province is a different quoting context.
        return (row.get('province'), row.get('car_id'),
                row.get('vehicle_year'), row.get('repair_type'),
                (row.get('source_url') or '').strip())
    for row in rows:
        url = (row.get('source_url') or '').strip()
        sum_insured = decimal_value(row.get('actual_sum_insured'))
        if url and sum_insured is not None:
            groups[detail_group_key(row)].add(sum_insured)

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
        url = (row.get('source_url') or '').strip()
        count_sums = len(groups[detail_group_key(row)]) if url else 0
        shared_url = count_sums > 1
        review_flags = []
        info_flags = []
        if status != 'DONE':
            review_flags.append(status or 'DETAIL_NOT_VERIFIED')
        if shared_url:
            # A single detail page is not necessarily specific to every sum.
            # Confirmed manually for BKI 15054 / CITY 2020 car 12.
            info_flags.append('SHARED_DETAIL_URL_MULTI_SUM')
        if diff is not None:
            if diff > 100:
                (info_flags if shared_url else review_flags).append(
                    'PREMIUM_DIFF_GT_100_SHARED_REFERENCE'
                    if shared_url else 'PREMIUM_DIFF_GT_100_UNEXPLAINED')
            elif diff > 1:
                (info_flags if shared_url else review_flags).append(
                    'PREMIUM_DIFF_1_TO_100_SHARED_REFERENCE'
                    if shared_url else 'PREMIUM_DIFF_1_TO_100_UNEXPLAINED')
            elif diff > 0:
                info_flags.append('PRICE_ROUNDING_LT_1')
        if not (row.get('insurer') or '').strip():
            review_flags.append('INSURER_NAME_MISSING')
        label = (row.get('package_name') or '').lower()
        if any(s in label for s in ('กรุงเทพ', 'กทม.', 'ปริมณฑล', '(bkk)', 'bangkok')):
            review_flags.append('PACKAGE_LOCATION_REVIEW')

        # Older Collector versions marked mismatches as REVIEW_REQUIRED.
        # Reinterpret the old note using the complete CSV's shared-URL context.
        legacy_notes = set((row.get('validation_notes') or '').split(';'))
        excluded = {'', 'DETAIL_OWN_DAMAGE_DIFFERS_FROM_LISTING_SUM'}
        if shared_url or (diff is not None and diff <= 1):
            excluded.add('DETAIL_PREMIUM_DIFFERS_FROM_LISTING')
        actual_notes = legacy_notes - excluded
        if status == 'DONE' and actual_notes:
            review_flags.append('VALIDATION_REVIEW_REQUIRED')

        review = bool(review_flags)
        price_context = (
            'DETAIL_NOT_AVAILABLE' if status != 'DONE'
            else 'SHARED_URL_PLAN_REFERENCE' if shared_url
            else 'DETAIL_PRICE_UNAVAILABLE' if detail_price is None
            else 'UNEXPLAINED_PRICE_DIFFERENCE' if diff is not None and diff > 1
            else 'MATCH_OR_ROUNDING')
        coverage_scope = (
            'PLAN_PAGE_REFERENCE_NOT_VERIFIED_FOR_EACH_SUM'
            if shared_url else 'DETAIL_PAGE_OBSERVATION')
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
            'shared_detail_url_distinct_sums': count_sums,
            'price_context_status': price_context,
            'detail_coverage_scope': coverage_scope,
            'premium_source_for_comparison': 'LISTING',
            'review_flags': ';'.join(review_flags),
            'information_flags': ';'.join(info_flags),
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
            'price_context_status', 'detail_coverage_scope',
            'premium_source_for_comparison',
            'review_flags', 'information_flags', 'needs_review']
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
        counters['SUM_MATCH:' + (row.get('sum_match_status') or '(blank)')] += 1
        counters['PRICE_CONTEXT:' + row['price_context_status']] += 1
        for flag in (row['review_flags'] or '').split(';'):
            if flag:
                counters['REVIEW_FLAG:' + flag] += 1
        for flag in (row['information_flags'] or '').split(';'):
            if flag:
                counters['INFO_FLAG:' + flag] += 1
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
