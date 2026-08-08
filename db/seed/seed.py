"""Loads db/seed/*.json into Postgres (local/dev/test only -- not run inside
the Agent Engine or Cloud Run production images). Reads DATABASE_URL from the
environment, e.g.:

    DATABASE_URL=postgresql+psycopg2://csrsupport:csrsupport@localhost:5432/csrsupport \
        python db/seed/seed.py

Idempotent: truncates the five tables (in FK-safe order) before reseeding, so
it's safe to rerun against a test database between test runs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

SEED_DIR = Path(__file__).parent
STRIP_PREFIX = "_"  # documentation keys like "_source"/"_note" are not columns


def _load(name: str) -> list[dict]:
    with open(SEED_DIR / f"{name}.json", encoding="utf-8") as f:
        rows = json.load(f)
    return [{k: v for k, v in row.items() if not k.startswith(STRIP_PREFIX)} for row in rows]


def seed(database_url: str) -> None:
    engine = create_engine(database_url)
    plans = _load("plans")
    rate_sheet = _load("rate_sheet")
    members = _load("members")
    accumulators = _load("member_accumulators")

    with engine.begin() as conn:
        # FK-safe truncate order: children before parents.
        conn.execute(text(
            "TRUNCATE quote_audit_log, member_accumulators, members, rate_sheet, plans CASCADE"
        ))

        for p in plans:
            conn.execute(
                text(
                    "INSERT INTO plans (plan_id, display_name, deductible_individual, "
                    "deductible_family, coinsurance_pct, oop_max_individual, oop_max_family, "
                    "preventive_covered_100pct_codes, prior_auth_required_codes, excluded_codes) "
                    "VALUES (:plan_id, :display_name, :deductible_individual, :deductible_family, "
                    ":coinsurance_pct, :oop_max_individual, :oop_max_family, "
                    ":preventive_covered_100pct_codes, :prior_auth_required_codes, :excluded_codes)"
                ),
                p,
            )

        for r in rate_sheet:
            conn.execute(
                text(
                    "INSERT INTO rate_sheet (cpt_code, common_name, search_aliases, negotiated_rate) "
                    "VALUES (:cpt_code, :common_name, :search_aliases, :negotiated_rate)"
                ),
                r,
            )

        for m in members:
            conn.execute(
                text(
                    "INSERT INTO members (member_id, first_name, last_name, plan_id, tier, "
                    "family_id, status, coverage_start, coverage_end) "
                    "VALUES (:member_id, :first_name, :last_name, :plan_id, :tier, :family_id, "
                    ":status, :coverage_start, :coverage_end)"
                ),
                m,
            )

        for a in accumulators:
            conn.execute(
                text(
                    "INSERT INTO member_accumulators (member_id, ind_ded_met, ind_oop_met, "
                    "fam_ded_met, fam_oop_met) "
                    "VALUES (:member_id, :ind_ded_met, :ind_oop_met, :fam_ded_met, :fam_oop_met)"
                ),
                a,
            )

    print(
        f"Seeded {len(plans)} plans, {len(rate_sheet)} rate_sheet rows, "
        f"{len(members)} members, {len(accumulators)} accumulator rows."
    )


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL environment variable is required")
    seed(url)
