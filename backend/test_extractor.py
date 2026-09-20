"""
test_extractor.py
-----------------
Smoke-test for the Transaction Extraction Agent.

Run from the project root (activate venv first):

    cd financial_tracker
    source .venv/bin/activate
    python3 backend/test_extractor.py

Each test case prints the full ExtractionResult so you can confirm
extraction is working before integrating with the Categorization Agent.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from agents.extractor import ExtractionAgent, TransactionType  # noqa: E402

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

# ---------------------------------------------------------------------------
# Test cases
# Each entry: (label, transcript, expected_count, spot_checks)
#
# spot_checks is a list of callables: (ExtractionResult) -> bool
# ---------------------------------------------------------------------------

TEST_CASES = [
    # 1. Single expense – western numerals
    (
        "Single expense (western numerals)",
        "دفعت 120 جنيه أوبر",
        1,
        [
            lambda r: r.transactions[0].amount == 120.0,
            lambda r: r.transactions[0].transaction_type == TransactionType.EXPENSE,
            lambda r: r.transactions[0].description == "أوبر",
            lambda r: r.transactions[0].currency == "EGP",
        ],
    ),
    # 2. Arabic words for numbers  – مية وعشرين = 120
    (
        "Arabic words for numbers (مية وعشرين جنيه أوبر)",
        "دفعت مية وعشرين جنيه في أوبر",
        1,
        [
            lambda r: r.transactions[0].amount == 120.0,
            lambda r: r.transactions[0].transaction_type == TransactionType.EXPENSE,
        ],
    ),
    # 3. Income transaction
    (
        "Income (قبضت 15000 جنيه)",
        "قبضت خمستاشر ألف جنيه",
        1,
        [
            lambda r: r.transactions[0].amount == 15000.0,
            lambda r: r.transactions[0].transaction_type == TransactionType.INCOME,
            lambda r: r.transactions[0].currency == "EGP",
        ],
    ),
    # 4. Multiple transactions in one sentence
    (
        "Multiple transactions (3 expenses)",
        "دفعت 120 جنيه أوبر و80 جنيه أكل و350 جنيه كتاب",
        3,
        [
            lambda r: len(r.transactions) == 3,
            lambda r: all(t.transaction_type == TransactionType.EXPENSE for t in r.transactions),
            lambda r: {t.amount for t in r.transactions} == {120.0, 80.0, 350.0},
        ],
    ),
    # 5. Mixed: income + expense in one sentence
    (
        "Mixed income & expense",
        "قبضت مرتبي خمسة عشر ألف جنيه ودفعت 500 جنيه إيجار",
        2,
        [
            lambda r: any(t.transaction_type == TransactionType.INCOME for t in r.transactions),
            lambda r: any(t.transaction_type == TransactionType.EXPENSE for t in r.transactions),
        ],
    ),
    # 6. Arabic-Indic numerals  ١٢٠
    (
        "Arabic-Indic numerals (١٢٠ جنيه)",
        "اشتريت كتاب بـ١٢٠ جنيه",
        1,
        [
            lambda r: r.transactions[0].amount == 120.0,
            lambda r: r.transactions[0].transaction_type == TransactionType.EXPENSE,
        ],
    ),
    # 7. No currency mentioned – should default to EGP
    (
        "No currency mentioned → defaults to EGP",
        "دفعت 50 على الغداء",
        1,
        [
            lambda r: r.transactions[0].currency == "EGP",
            lambda r: r.transactions[0].amount == 50.0,
        ],
    ),
    # 8. No transaction at all – must return empty list
    (
        "No transaction (unrelated text) → empty list",
        "الجو جميل النهاردة",
        0,
        [
            lambda r: r.transactions == [],
        ],
    ),
    # 9. مرتبي (salary) → income
    (
        "Salary phrasing (مرتبي) → income",
        "مرتبي النهاردة 12000 جنيه",
        1,
        [
            lambda r: r.transactions[0].transaction_type == TransactionType.INCOME,
            lambda r: r.transactions[0].amount == 12000.0,
        ],
    ),
    # 10. Description must NOT be translated/categorised
    (
        "Description preserved as Arabic (no category)",
        "اشتريت عيش بعشرة جنيه",
        1,
        [
            lambda r: r.transactions[0].description != "food",
            lambda r: r.transactions[0].description != "bread",
            lambda r: r.transactions[0].amount == 10.0,
        ],
    ),
]


def run_spot_checks(label, result, checks):
    all_ok = True
    for idx, check in enumerate(checks):
        try:
            ok = check(result)
        except Exception as e:
            ok = False
            print(f"       check[{idx}] EXCEPTION: {e}")
        if not ok:
            print(f"       {FAIL} check[{idx}] failed")
            all_ok = False
    return all_ok


def main() -> None:
    agent = ExtractionAgent()
    passed = 0
    failed = 0

    print("\n" + "=" * 70)
    print(" Transaction Extraction Agent — Smoke Test")
    print("=" * 70 + "\n")

    for label, transcript, expected_count, spot_checks in TEST_CASES:
        result = agent.extract_transactions(transcript)
        count_ok = len(result.transactions) == expected_count
        checks_ok = run_spot_checks(label, result, spot_checks)
        ok = count_ok and checks_ok
        status = PASS if ok else FAIL
        tag    = "PASS" if ok else "FAIL"

        print(f"{status} [{tag}]  {label}")
        print(f"       transcript : {transcript!r}")
        print(f"       expected   : {expected_count} transaction(s)")
        print(f"       got        : {len(result.transactions)} transaction(s)")
        for i, tx in enumerate(result.transactions):
            print(
                f"         [{i}] amount={tx.amount}  currency={tx.currency}"
                f"  type={tx.transaction_type.value}  desc={tx.description!r}"
            )
        print()

        if ok:
            passed += 1
        else:
            failed += 1

    print("=" * 70)
    print(f" Results: {passed}/{passed + failed} passed")
    print("=" * 70 + "\n")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
