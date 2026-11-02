"""SQLite adapter for the existing ANC MySQL collector (v4 table shape).

This module intentionally preserves the existing record/target/branch/checkpoint
keys and original Collector SQL logic. It does NOT migrate any MySQL data.
Uses only Python's standard library and keeps the DB local to the workstation.
"""
from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

sqlite3.register_adapter(Decimal, lambda value: str(value))


class SQLiteCursor:
    """Small PyMySQL-compatible cursor for SQL used by anc_collector.Database."""

    def __init__(self, parent: "SQLiteConnection"):
        self.parent = parent
        self.inner = parent.raw.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.inner.close()

    @property
    def description(self):
        return self.inner.description

    @property
    def rowcount(self):
        return self.inner.rowcount

    def execute(self, sql, params=None):
        query = str(sql).replace("%s", "?")
        query = re.sub(r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", query, flags=re.I)

        if re.search(r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b", query, flags=re.I):
            table_match = re.search(
                r"\bINSERT\s+INTO\s+[\`\"]?([a-zA-Z0-9_]+)", query, flags=re.I
            )
            if not table_match:
                raise ValueError("Cannot identify SQLite UPSERT table")
            table = table_match.group(1)
            conflict_key = self.parent.conflict_keys.get(table)
            if not conflict_key:
                raise ValueError(f"No registered SQLite conflict key for {table}")
            query = re.sub(
                r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b",
                f'ON CONFLICT("{conflict_key}") DO UPDATE SET',
                query, flags=re.I,
            )
            query = re.sub(
                r"\bVALUES\s*\(\s*[\`\"]?([a-zA-Z0-9_]+)[\`\"]?\s*\)",
                r'excluded."\1"',
                query, flags=re.I,
            )

        if params is None:
            self.inner.execute(query)
        else:
            self.inner.execute(query, tuple(params))
        return self

    def fetchone(self):
        row = self.inner.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.inner.fetchall()]

    def fetchmany(self, size=1):
        return [dict(row) for row in self.inner.fetchmany(size)]


class SQLiteConnection:
    """Connection adapter preserving the Collector's cursor/commit interface."""

    def __init__(self, filename: str | Path):
        self.filename = Path(filename).expanduser().resolve()
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.raw = sqlite3.connect(str(self.filename), timeout=30)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA busy_timeout = 30000")
        self.raw.execute("PRAGMA journal_mode = WAL")
        self.conflict_keys: dict[str, str] = {}
        self._closed = False

    @property
    def open(self) -> bool:
        return not self._closed

    def cursor(self):
        if self._closed:
            raise sqlite3.ProgrammingError("SQLite connection is closed")
        return SQLiteCursor(self)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        if not self._closed:
            self.raw.close()
            self._closed = True

    def initialize_schema(self, records: str, targets: str, branches: str,
                          checkpoints: str):
        names = (records, targets, branches, checkpoints)
        if not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", x) for x in names):
            raise ValueError("Unsafe SQLite table name")

        self.conflict_keys = {
            records: "record_key", targets: "target_key",
            branches: "branch_key", checkpoints: "record_key"
        }

        # Money stored as decimal TEXT (e.g. "10123.45"), not binary float.
        # This preserves 2-decimal source precision; consumers can cast/parse.
        money_fields = [
            "premium", "net_premium", "original_premium", "actual_sum_insured",
            "deductible", "coverage_bodily_injury_person",
            "coverage_bodily_injury_accident", "coverage_third_party_property",
            "coverage_own_damage", "coverage_fire_theft", "coverage_flood",
            "personal_accident", "medical_expense", "bail_bond"
        ]
        amount_ddl = ",\n".join(f'"{f}" TEXT' for f in money_fields)

        self.raw.executescript(f"""
        CREATE TABLE IF NOT EXISTS "{records}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_key TEXT NOT NULL UNIQUE,
            branch_key TEXT NOT NULL,
            target_key TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            listing_url TEXT,
            region TEXT NOT NULL,
            province TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            submodel TEXT,
            car_id INTEGER NOT NULL,
            vehicle_year INTEGER NOT NULL,
            insurance_type TEXT NOT NULL,
            repair_type TEXT NOT NULL,
            insurer TEXT,
            insurer_code TEXT,
            package_id TEXT,
            package_name TEXT,
            {amount_ddl},
            listing_status TEXT NOT NULL,
            detail_status TEXT NOT NULL,
            validation_status TEXT NOT NULL,
            validation_notes TEXT,
            raw_listing TEXT,
            raw_detail TEXT,
            collected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_anc_record_target" ON "{records}"(target_key);
        CREATE INDEX IF NOT EXISTS "idx_anc_record_branch" ON "{records}"(branch_key);
        CREATE INDEX IF NOT EXISTS "idx_anc_record_vehicle" ON "{records}"(brand, model, vehicle_year);
        CREATE INDEX IF NOT EXISTS "idx_anc_record_province" ON "{records}"(province);
        CREATE INDEX IF NOT EXISTS "idx_anc_record_detail" ON "{records}"(detail_status);

        CREATE TABLE IF NOT EXISTS "{targets}" (
            target_key TEXT PRIMARY KEY,
            region TEXT NOT NULL,
            province TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            vehicle_year INTEGER NOT NULL,
            status TEXT NOT NULL,
            total_submodels INTEGER NOT NULL DEFAULT 0,
            complete_branches INTEGER NOT NULL DEFAULT 0,
            total_branches INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_anc_target_status" ON "{targets}"(status);

        CREATE TABLE IF NOT EXISTS "{branches}" (
            branch_key TEXT PRIMARY KEY,
            target_key TEXT NOT NULL,
            car_id INTEGER NOT NULL,
            repair_type TEXT NOT NULL,
            status TEXT NOT NULL,
            listing_url TEXT,
            package_count INTEGER NOT NULL DEFAULT 0,
            saved_count INTEGER NOT NULL DEFAULT 0,
            detail_done INTEGER NOT NULL DEFAULT 0,
            detail_unavailable INTEGER NOT NULL DEFAULT 0,
            listing_issues TEXT,
            error_message TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_anc_branch_target" ON "{branches}"(target_key);
        CREATE INDEX IF NOT EXISTS "idx_anc_branch_status" ON "{branches}"(status);

        CREATE TABLE IF NOT EXISTS "{checkpoints}" (
            record_key TEXT PRIMARY KEY,
            branch_key TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_anc_checkpoint_branch" ON "{checkpoints}"(branch_key);
        CREATE INDEX IF NOT EXISTS "idx_anc_checkpoint_status" ON "{checkpoints}"(status);
        """)
        self.raw.commit()
