"""Optional Smart Continue controller for ANCBroker.

Preserves the existing anc_full_run.py default stop-on-error behavior.
On an unexpected batch process exit, uses persisted target statuses to
isolate only uncompleted targets, while stopping on systemic failures.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

TOTAL_TARGETS = 480
TERMINAL = {"DONE", "PARTIAL", "FAILED"}
STOP_CODES = {75: "REQUEST_BUDGET", 76: "SITE_BLOCKED", 77: "QUALITY_STOP", 78: "DATABASE_ERROR"}
TABLE_TARGET = "anc_competitor_target_v4"
TABLE_RECORD = "anc_competitor_insurance_v4"


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def snapshot(db_path):
    """Read-only status from the existing SQLite checkpoint database."""
    path = Path(db_path)
    if not path.exists():
        return {"records": 0, "details": 0, "statuses": {}}
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if TABLE_TARGET not in tables and TABLE_RECORD not in tables:
            return {"records": 0, "details": 0, "statuses": {}}
        if TABLE_TARGET not in tables or TABLE_RECORD not in tables:
            raise sqlite3.DatabaseError("Collector database missing one of the required tables")
        records = db.execute(f"SELECT COUNT(*) FROM {TABLE_RECORD}").fetchone()[0]
        details = db.execute(
            f"SELECT COUNT(*) FROM {TABLE_RECORD} WHERE detail_status='DONE'"
        ).fetchone()[0]
        rows = db.execute(
            f"SELECT province, brand, model, vehicle_year, status FROM {TABLE_TARGET}"
        ).fetchall()
        statuses = {(r["province"], r["brand"], r["model"], int(r["vehicle_year"])): r["status"]
                    for r in rows}
    return {"records": records, "details": details, "statuses": statuses}


def planned_targets():
    # Importing does not make any HTTP requests or touch database tables.
    from anc_collector import PROVINCES, VEHICLES
    return [(province, v.brand, v.model, int(v.year))
            for _, province in PROVINCES for v in VEHICLES]


def log_issue(folder, batch_start, batch_end, index, key, reason, code, logfile):
    path = folder / "errors.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        if new:
            writer.writerow(["when", "batch_start", "batch_end", "target_index",
                             "province", "brand", "model", "year",
                             "reason", "exit_code", "log_file"])
        writer.writerow([timestamp(), batch_start, batch_end, index or "",
                         *(key or ("", "", "", "")), reason, code, str(logfile or "")])


def run_child(folder, args, db, output, start, end, export_only=False):
    """One sequential child process, with its own preserved UTF-8 log."""
    label = "export" if export_only else f"{start:03d}_{end:03d}"
    number = 1
    while (folder / f"{label}_try{number}.log").exists():
        number += 1
    logfile = folder / f"{label}_try{number}.log"
    command = [sys.executable, "anc_collector.py",
               "--db-backend", "sqlite", "--sqlite-path", str(db),
               "--output", str(output)]
    if export_only:
        command.append("--export-only")
    else:
        command += ["--start-index", str(start), "--end-index", str(end),
                    "--resume", "--delay", str(args.delay),
                    "--max-requests", str(args.max_requests)]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PYTHONUTF8"] = "1"
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"
    print(f"START {label} | log={logfile}", flush=True)
    with logfile.open("w", encoding="utf-8", errors="replace") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                env=env, check=False)
    print(f"END {label} | exit={result.returncode}", flush=True)
    return result.returncode, logfile


def status_for(statuses, targets, index):
    return statuses.get(targets[index - 1], "NOT_COLLECTED")


def report_batch(folder, start, end, before, after, targets, problems):
    if after["records"] < before["records"]:
        raise sqlite3.DatabaseError("Record count decreased unexpectedly")
    values = [status_for(after["statuses"], targets, i) for i in range(start, end + 1)]
    batch = {
        "as_of": timestamp(),
        "batch": [start, end],
        "records_before": before["records"],
        "records_after": after["records"],
        "records_added": after["records"] - before["records"],
        "detail_done_total": after["details"],
        "status_counts": dict(Counter(values)),
        "unresolved_indexes": [i for i, s in zip(range(start, end + 1), values)
                               if s not in TERMINAL],
        "process_errors_this_batch": problems,
    }
    path = folder / f"checkpoint_{start:03d}_{end:03d}.json"
    path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print("QA", json.dumps(batch, ensure_ascii=False), flush=True)
    return batch


def main(argv=None):
    parser = argparse.ArgumentParser(description="ANC Smart Continue: complete what is possible; report the rest")
    parser.add_argument("--db", default="anc_full_24provinces.sqlite3")
    parser.add_argument("--output", default="anc_full_24provinces.csv")
    parser.add_argument("--run-dir", default="anc_full_run")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--max-requests", type=int, default=18000)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=TOTAL_TARGETS)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--max-errors", type=int, default=30)
    args = parser.parse_args(argv)
    if not (1 <= args.start_index <= args.end_index <= TOTAL_TARGETS):
        parser.error("Indexes must be within 1..480")
    if (args.batch_size < 1 or args.delay < .2 or args.max_requests < 100
            or args.max_consecutive_errors < 1 or args.max_errors < 1):
        parser.error("Invalid safety limits")

    folder = Path(args.run_dir)
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".full_run.lock"  # shared with regular full runner
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"smart:{os.getpid()}")
    except FileExistsError:
        print("STOP: existing full-run lock. Check that no collector is running:", lock)
        return 2

    errors = 0
    consecutive_errors = 0
    warning_count = 0
    db_path = Path(args.db).resolve()
    output_path = Path(args.output).resolve()
    try:
        targets = planned_targets()
        if len(targets) != TOTAL_TARGETS:
            print("STOP: target scope changed; check source requirements")
            return 78
        for start in range(args.start_index, args.end_index + 1, args.batch_size):
            end = min(start + args.batch_size - 1, args.end_index)
            before = snapshot(db_path)
            code, log = run_child(folder, args, db_path, output_path, start, end)
            if code == 75:  # a bounded retry; do not loop without limit
                print("HTTP budget reached: retry same batch once with resume")
                code, log = run_child(folder, args, db_path, output_path, start, end)
            if code in STOP_CODES or code == 130 or code < 0:
                print(f"STOP: systemic condition, exit={code}, log={log}")
                return code if code > 0 else 130

            batch_errors = 0
            if code != 0:
                errors += 1
                batch_errors += 1
                warning_count += 1
                log_issue(folder, start, end, None, None,
                          "BATCH_PROCESS_ERROR: isolate unfinished targets", code, log)
                # A Python crash late in a batch can happen after all targets
                # were committed. Do not re-fetch already terminal targets.
                state = snapshot(db_path)
                remaining = [i for i in range(start, end + 1)
                             if status_for(state["statuses"], targets, i) not in TERMINAL]
                print(f"Batch failed; unfinished targets: {remaining}", flush=True)
                for index in remaining:
                    code_one, log_one = run_child(folder, args, db_path, output_path,
                                                  index, index)
                    if code_one in STOP_CODES or code_one == 130 or code_one < 0:
                        print(f"STOP: systemic error on target {index}, log={log_one}")
                        return code_one if code_one > 0 else 130
                    if code_one != 0:
                        errors += 1
                        batch_errors += 1
                        warning_count += 1
                        consecutive_errors += 1
                        log_issue(folder, start, end, index, targets[index - 1],
                                  "TARGET_PROCESS_ERROR", code_one, log_one)
                        if (consecutive_errors >= args.max_consecutive_errors
                                or errors >= args.max_errors):
                            print("STOP: repeated process failures; inspect errors.csv")
                            return 77
                    else:
                        consecutive_errors = 0
                # If previous run crashed before audit/export, repair it from
                # saved SQLite without fetching any website pages.
                exported, export_log = run_child(folder, args, db_path, output_path,
                                                 start, end, export_only=True)
                if exported != 0:
                    errors += 1
                    warning_count += 1
                    log_issue(folder, start, end, None, None,
                              "CSV_AUDIT_EXPORT_FAILED", exported, export_log)
                    if errors >= args.max_errors:
                        return 77
            else:
                consecutive_errors = 0

            after = snapshot(db_path)
            check = report_batch(folder, start, end, before, after, targets, batch_errors)
            if len(check["unresolved_indexes"]) > 0:
                warning_count += len(check["unresolved_indexes"])
                for index in check["unresolved_indexes"]:
                    log_issue(folder, start, end, index, targets[index - 1],
                              "UNRESOLVED_AFTER_BATCH", "", log)

            failures = check["status_counts"].get("FAILED", 0)
            if (check["records_added"] == 0
                    and failures >= max(3, int(.8 * (end - start + 1)))):
                print("STOP: zero new offers plus widespread target failures")
                return 77

        print("ALL REQUESTED TARGETS ATTEMPTED. Inspect errors.csv and checkpoint JSON.")
        print("DB:", db_path)
        print("CSV:", output_path)
        print("AUDIT: anc_audit_output/anc_audit_summary.csv")
        if warning_count:
            print(f"FINISHED WITH WARNINGS: {warning_count}; no data silently discarded")
            return 79
        print("FINISHED: no unhandled process errors")
        return 0
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
        print(f"STOP: SQLite problem: {exc}")
        return 78
    except KeyboardInterrupt:
        print("INTERRUPTED: previously committed SQLite records remain. Resume with same command.")
        return 130
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
