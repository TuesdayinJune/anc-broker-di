"""Run all 480 ANCBroker targets in batches with SQLite checkpoints.

One command, no concurrent collectors. Stop on site block, bounded HTTP budget,
or sustained technical failures. Audit snapshot after every batch.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


def overview(db_path, start, end):
    if not Path(db_path).exists():
        return {"records": 0, "detail_done": 0, "detail_unavailable": 0,
                "targets": {}, "current_batch": []}
    with sqlite3.connect(str(db_path), timeout=30) as db:
        db.row_factory = sqlite3.Row
        def scalar(sql):
            try:
                return db.execute(sql).fetchone()[0]
            except sqlite3.OperationalError:
                return 0
        records = scalar("SELECT COUNT(*) FROM anc_competitor_insurance_v4")
        done = scalar("SELECT COUNT(*) FROM anc_competitor_insurance_v4 WHERE detail_status='DONE'")
        unavailable = scalar("SELECT COUNT(*) FROM anc_competitor_insurance_v4 WHERE detail_status='DETAIL_UNAVAILABLE'")
        try:
            rows = [dict(r) for r in db.execute(
                "SELECT province,brand,model,vehicle_year,status FROM anc_competitor_target_v4"
            )]
        except sqlite3.OperationalError:
            rows = []
    return {
        "records": records, "detail_done": done,
        "detail_unavailable": unavailable,
        "targets": dict(__import__("collections").Counter(r["status"] for r in rows)),
        "target_rows": rows,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Full ANC collection with resumable 20-target batches")
    p.add_argument("--db", default="anc_full_24provinces.sqlite3")
    p.add_argument("--output", default="anc_full_24provinces.csv")
    p.add_argument("--run-dir", default="anc_full_run")
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--delay", type=float, default=3.0)
    p.add_argument("--max-requests", type=int, default=18000)
    p.add_argument("--start-index", type=int, default=1)
    p.add_argument("--end-index", type=int, default=480)
    args = p.parse_args(argv)
    if not (1 <= args.start_index <= args.end_index <= 480):
        p.error("target indexes must be between 1 and 480")
    if args.batch_size < 1 or args.delay < 0.2 or args.max_requests < 100:
        p.error("invalid batch size, delay or request budget")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = run_dir / ".full_run.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(str(os.getpid()))
    except FileExistsError:
        print("Another run may be active. Check process before removing:", lock)
        return 2

    db = Path(args.db).resolve()
    output = Path(args.output).resolve()
    try:
        for start in range(args.start_index, args.end_index + 1, args.batch_size):
            end = min(args.end_index, start + args.batch_size - 1)
            before = overview(db, start, end)
            attempts = 0
            while True:
                attempts += 1
                command = [
                    sys.executable, "anc_collector.py",
                    "--db-backend", "sqlite",
                    "--sqlite-path", str(db),
                    "--start-index", str(start),
                    "--end-index", str(end),
                    "--delay", str(args.delay),
                    "--max-requests", str(args.max_requests),
                    "--resume", "--output", str(output),
                ]
                logfile = run_dir / f"batch_{start:03d}_{end:03d}_try{attempts}.log"
                print(f"START targets {start}-{end}/480 attempt {attempts}; log {logfile}", flush=True)
                with logfile.open("w", encoding="utf-8", errors="replace") as log:
                    proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                          check=False)
                print(f"Finished targets {start}-{end}; exit={proc.returncode}", flush=True)
                if proc.returncode == 75 and attempts < 2:
                    print("Request budget reached; restart same batch with --resume", flush=True)
                    continue
                if proc.returncode in (75, 76, 77):
                    print(f"STOP: request budget/site restriction/quality stop ({proc.returncode}). Saved data remains. See {logfile}", flush=True)
                    return proc.returncode
                if proc.returncode != 0:
                    print(f"STOP: collector error. See {logfile}; resume by rerunning same command.", flush=True)
                    return proc.returncode
                break

            after = overview(db, start, end)
            added = after["records"] - before["records"]
            # Failed targets may be ordinary no-offer cases; stop only for a
            # sustained zero-yield batch dominated by technical failures.
            from anc_collector import PROVINCES, VEHICLES
            planned = [(p, v.brand, v.model, v.year)
                       for _, p in PROVINCES for v in VEHICLES][start-1:end]
            rows = { (r["province"], r["brand"], r["model"], r["vehicle_year"]): r["status"]
                     for r in after.get("target_rows", []) }
            statuses = [rows.get(x, "NOT_COLLECTED") for x in planned]
            failure_count = sum(x in ("FAILED", "BLOCKED") for x in statuses)
            report = {
                "as_of": datetime.now().isoformat(timespec="seconds"),
                "batch": [start, end], "records_total": after["records"],
                "new_records": added, "detail_done_total": after["detail_done"],
                "detail_unavailable_total": after["detail_unavailable"],
                "batch_statuses": dict(__import__("collections").Counter(statuses)),
            }
            (run_dir / f"checkpoint_{start:03d}_{end:03d}.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("QA", json.dumps(report, ensure_ascii=False), flush=True)
            if after["records"] < before["records"]:
                print("STOP: DB record count decreased unexpectedly", flush=True)
                return 78
            if added == 0 and failure_count >= max(3, int(0.8 * len(planned))):
                print("STOP: high failure rate and zero new offers; inspect log before continuing.", flush=True)
                return 77
        print("ALL REQUESTED BATCHES ATTEMPTED. Review target statuses; not all details need be DONE.")
        print("SQLite:", db)
        print("CSV:", output)
        print("Audit:", Path("anc_audit_output") / "anc_audit_summary.csv")
        return 0
    except KeyboardInterrupt:
        print("Interrupted; SQLite checkpoints remain. Re-run same command to resume.")
        return 130
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
