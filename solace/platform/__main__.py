"""Manage counsellor accounts.

uv run python -m solace.platform add-counsellor --email nimal@example.org --name "Nimal"
uv run python -m solace.platform list
uv run python -m solace.platform disable --email nimal@example.org
"""

import argparse
import getpass
import sys

from solace.config import get_settings
from solace.platform.store import PlatformStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m solace.platform")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-counsellor", help="create a counsellor account (asks for a password)")
    add.add_argument("--email", required=True)
    add.add_argument("--name", required=True)
    sub.add_parser("list", help="list counsellor accounts")
    for name in ("disable", "enable"):
        p = sub.add_parser(name, help=f"{name} a counsellor account")
        p.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    store = PlatformStore(get_settings().solace_db_path)
    if args.cmd == "add-counsellor":
        password = getpass.getpass("Password (at least 12 characters): ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords don't match.", file=sys.stderr)
            return 1
        try:
            c = store.add_counsellor(args.email, args.name, password)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Added {c.name} <{c.email}>")
    elif args.cmd == "list":
        for c, active in store.list_counsellors():
            print(f"{c.name:24} {c.email:32} {'active' if active else 'disabled'}")
    else:
        if not store.set_active(args.email, args.cmd == "enable"):
            print("No account with that email.", file=sys.stderr)
            return 1
        print(f"{args.cmd.capitalize()}d {args.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
