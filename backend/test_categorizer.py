"""
test_categorizer.py
-------------------
Smoke-test for the Categorization Agent.

Run from the project root (activate venv first):

    cd financial_tracker
    source .venv/bin/activate
    python3 backend/test_categorizer.py

Each test confirms:
  - The correct category is assigned.
  - The original amount, currency, description, and transaction_type are unchanged.
  - The output count matches the input count.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from agents.extractor.schemas import Transaction, TransactionType  # noqa: E402
from agents.categorizer import CategorizationAgent, Category        # noqa: E402

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


def make(description: str, amount: float = 100.0,
         ttype: str = "expense", currency: str = "EGP") -> Transaction:
    return Transaction(
        amount=amount,
        currency=currency,
        description=description,
        transaction_type=ttype,
    )


# ---------------------------------------------------------------------------
# Test cases: (label, list_of_transactions, list_of_expected_categories)
# ---------------------------------------------------------------------------

TEST_CASES = [
    # 1. Transportation — Uber
    (
        "Uber → transportation",
        [make("أوبر", 120)],
        [Category.TRANSPORTATION],
    ),
    # 2. Food — restaurant
    (
        "مطعم → food",
        [make("مطعم", 80)],
        [Category.FOOD],
    ),
    # 3. Education — book
    (
        "كتاب → education",
        [make("كتاب", 350)],
        [Category.EDUCATION],
    ),
    # 4. Income — salary
    (
        "مرتب → income",
        [make("مرتب", 15000, ttype="income")],
        [Category.INCOME],
    ),
    # 5. Healthcare — pharmacy
    (
        "صيدلية → healthcare",
        [make("صيدلية", 200)],
        [Category.HEALTHCARE],
    ),
    # 6. Entertainment — cinema
    (
        "سينما → entertainment",
        [make("سينما", 150)],
        [Category.ENTERTAINMENT],
    ),
    # 7. Bills — electricity
    (
        "كهرباء → bills",
        [make("كهرباء", 400)],
        [Category.BILLS],
    ),
    # 8. Housing — rent
    (
        "إيجار → housing",
        [make("إيجار", 5000)],
        [Category.HOUSING],
    ),
    # 9. Multiple transactions in one call (batch)
    (
        "Batch: أوبر + مطعم + كتاب",
        [make("أوبر", 120), make("مطعم", 80), make("كتاب", 350)],
        [Category.TRANSPORTATION, Category.FOOD, Category.EDUCATION],
    ),
    # 10. Egyptian colloquial: كريم (Careem) → transportation
    (
        "كريم → transportation (Egyptian colloquial)",
        [make("كريم", 90)],
        [Category.TRANSPORTATION],
    ),
    # 11. Egyptian colloquial: بيتزا → food
    (
        "بيتزا → food (Egyptian colloquial)",
        [make("بيتزا", 180)],
        [Category.FOOD],
    ),
    # 12. Ambiguous description → other
    (
        "غريب → other (ambiguous)",
        [make("شيء غريب جداً", 50)],
        [Category.OTHER],
    ),
]


def check_fields_unchanged(original: Transaction, result_txn) -> bool:
    """Verify no original field was mutated."""
    ok = True
    if result_txn.amount != original.amount:
        print(f"         ✗ amount changed: {original.amount} → {result_txn.amount}")
        ok = False
    if result_txn.description != original.description:
        print(f"         ✗ description changed: {original.description!r} → {result_txn.description!r}")
        ok = False
    if result_txn.transaction_type != original.transaction_type:
        print(f"         ✗ transaction_type changed")
        ok = False
    if result_txn.currency != original.currency:
        print(f"         ✗ currency changed")
        ok = False
    return ok


def main() -> None:
    agent = CategorizationAgent()
    passed = 0
    failed = 0

    print("\n" + "=" * 70)
    print(" Categorization Agent — Smoke Test")
    print("=" * 70 + "\n")

    for label, transactions, expected_cats in TEST_CASES:
        result = agent.categorize_transactions(transactions)

        # Count check
        count_ok = len(result.transactions) == len(transactions)

        # Category check
        cats_ok = True
        for i, (exp, got_txn) in enumerate(zip(expected_cats, result.transactions)):
            if got_txn.category != exp:
                cats_ok = False

        # Field integrity check
        fields_ok = all(
            check_fields_unchanged(orig, got)
            for orig, got in zip(transactions, result.transactions)
        )

        ok = count_ok and cats_ok and fields_ok
        status = PASS if ok else FAIL
        tag    = "PASS" if ok else "FAIL"

        print(f"{status} [{tag}]  {label}")
        for i, txn in enumerate(result.transactions):
            exp_str = expected_cats[i].value if i < len(expected_cats) else "?"
            match   = "✓" if txn.category.value == exp_str else "✗"
            print(
                f"         [{i}] {match} desc={txn.description!r:20s}  "
                f"got={txn.category.value:15s}  expected={exp_str}"
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
