"""
Build the SQLite database from schema.sql + seed.sql.


"""

import os
import sqlite3
import sys

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "plm-iq.db")
SCHEMA = os.path.join(DB_DIR, "schema.sql")
SEED = os.path.join(DB_DIR, "seed.sql")

TABLES = [
    "tenants",
    "users",
    "roles",
    "parts",
    "bom",
    "costing_bom",
    "engineering_change_orders",
    "approved_manufacturer_list",
    "approved_vendor_list",
    "cad_metadata",
    "documents",
    "workflow_definitions",
    "workflow_instances",
    "workflow_tasks",
    "notifications",
    "favorites",
    "plmiq_node",
    "plmiq_edge_type",
    "plmiq_edge",
    "plmiq_edge_annotation",
    "plmiq_edge_evidence",
    "plmiq_edge_impact",
]


def step(label, description):
    print(f"  [{label}] {description}")


def main():
    print()
    print("  PLM-IQ - Database Initialization")
    print("  " + "-" * 40)

    # Step 1: Remove existing database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        step("1/4", "Removed existing database")
    else:
        step("1/4", "No existing database found")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # Step 2: Apply schema
        step("2/4", "Applying schema...")
        with open(SCHEMA, encoding="utf-8") as f:
            conn.executescript(f.read())
        step("2/4", "Schema applied successfully")

        # Step 3: Apply seed data
        step("3/4", "Seeding data...")
        with open(SEED, encoding="utf-8") as f:
            conn.executescript(f.read())
        step("3/4", "Seed data applied successfully")

        # Step 4: Verify
        step("4/4", "Verifying database...")

        c.execute("PRAGMA integrity_check;")
        integrity = c.fetchone()[0]
        print(f"         Integrity: {integrity}")

        c.execute("PRAGMA foreign_key_check;")
        fk_violations = c.fetchall()
        print(f"         FK violations: {len(fk_violations)}")
        if fk_violations:
            for row in fk_violations:
                print(f"           - {row}")
            print("         WARNING: Foreign key violations found!")

        for table in TABLES:
            c.execute(f"SELECT COUNT(*) FROM {table};")
            count = c.fetchone()[0]
            print(f"         {table}: {count} rows")

        conn.commit()
        step("4/4", "Verification complete")

        print()
        print("  " + "-" * 40)
        print(f"  Database: {DB_PATH}")
        print(f"  Status:   OK")
        print()

    except Exception as e:
        conn.close()
        print(f"\n  [ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    conn.close()


if __name__ == "__main__":
    main()
