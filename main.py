#!/usr/bin/env python3
"""Omni Copilot — CLI chat interface v2."""

import json
from orchestrator import Orchestrator

BANNER = """
╔══════════════════════════════════════════╗
║         OMNI COPILOT v0.2               ║
║   Planning · Memory · Multi-Agent       ║
╚══════════════════════════════════════════╝

Commands:
  /schedule   — schedule a meeting + send invite
  /email      — send an email
  /summarize  — search and summarize
  /inbox      — check inbox
  /calendar   — list events
  /meet       — schedule + invite
  /auto       — toggle auto mode
  /memory     — show memory
  /tools      — list all tools
  /help       — show this message
  /quit       — exit

Just type naturally:
  "prepare a meeting with alice@acme.com"
  "search for roadmap and email summary"
  "schedule meeting and send slack to #team"
"""


def format_result(r: dict) -> str:
    ok = r.get("ok", False)
    status = "OK" if ok else "FAIL"
    payload = json.dumps(r.get("result", r.get("error", r)), indent=2, default=str)
    return f"  [{status}] {payload}"


def main():
    orch = Orchestrator()
    print(BANNER)

    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input == "/quit":
            print("Bye!")
            break
        if user_input == "/auto":
            orch.auto_mode = not orch.auto_mode
            print(f"  Auto mode: {'ON' if orch.auto_mode else 'OFF'}")
            continue
        if user_input == "/memory":
            for entry in orch.get_memory(limit=5):
                print(f"  [{entry.get('timestamp', '?')}] {entry.get('query', '?')}")
            continue
        if user_input == "/tools":
            for t in orch.get_all_tools():
                print(f"  {t['name']:30s} — {t['description']}")
            continue
        if user_input == "/help":
            print(BANNER)
            continue

        response = orch.process(user_input)

        # Show plan
        plan = response.get("plan", [])
        if plan:
            print(f"\n  Plan ({len(plan)} steps):")
            for s in plan:
                print(f"    {s['step']}. {s['label']}")

        # Show results
        print()
        for r in response.get("results", []):
            print(format_result(r))

        # Show log summary
        log = response.get("log", [])
        if log:
            print(f"\n  Log: {len(log)} entries")


if __name__ == "__main__":
    main()
