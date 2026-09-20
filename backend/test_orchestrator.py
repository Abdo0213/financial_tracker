"""
test_orchestrator.py
---------------------
Minimal smoke-test for the Orchestrator Agent.

Run from the project root:

    cd financial_tracker
    pip install -r requirements.txt
    OPENAI_API_KEY=sk-... python backend/test_orchestrator.py

Each test case prints the full OrchestratorResult so you can quickly
confirm the agent is working before integrating with the rest of the backend.
"""

import sys
import os

# Allow running from the project root without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from agents.orchestrator import OrchestratorAgent, Intent  # noqa: E402

TEST_CASES = [
    # (transcript, expected_intent)
    ("دفعت 120 جنيه أوبر",                    Intent.ADD_TRANSACTION),
    ("اشتريت كتاب بـ350 جنيه",               Intent.ADD_TRANSACTION),
    ("قبضت 15000 جنيه",                       Intent.ADD_TRANSACTION),
    ("أنا صرفت كام النهاردة؟",               Intent.QUERY_TRANSACTIONS),
    ("وريني مصاريفي",                         Intent.QUERY_TRANSACTIONS),
    ("صرفي على الأكل كام؟",                  Intent.QUERY_TRANSACTIONS),
    ("الأوبر اللي سجلته كان 150 مش 120",     Intent.UPDATE_TRANSACTION),
    ("غير آخر عملية",                         Intent.UPDATE_TRANSACTION),
    ("امسح آخر عملية",                        Intent.DELETE_TRANSACTION),
    ("احذف مصروف الأوبر",                    Intent.DELETE_TRANSACTION),
    ("مرحبا ازيك",                            Intent.UNKNOWN),
]

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


def main() -> None:
    agent = OrchestratorAgent()

    passed = 0
    failed = 0

    print("\n" + "=" * 65)
    print(" Orchestrator Agent — Smoke Test")
    print("=" * 65 + "\n")

    for transcript, expected in TEST_CASES:
        result = agent.orchestrate(transcript)
        ok = result.intent == expected
        status = PASS if ok else FAIL
        label = "PASS" if ok else "FAIL"

        print(f"{status} [{label}]  {transcript!r}")
        print(f"       intent     : {result.intent.value}")
        print(f"       expected   : {expected.value}")
        print(f"       confidence : {result.confidence:.2f}")
        print(f"       reasoning  : {result.reasoning}")
        print()

        if ok:
            passed += 1
        else:
            failed += 1

    print("=" * 65)
    print(f" Results: {passed}/{passed + failed} passed")
    print("=" * 65 + "\n")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
