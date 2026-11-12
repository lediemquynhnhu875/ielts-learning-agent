"""Manual alternative to automatic startup migrations for the development schema."""

import argparse
from ...core.config import Settings


def main():
    parser = argparse.ArgumentParser(description="Initialize the UC-04 development PostgreSQL schema")
    parser.add_argument("command", choices=["init"])
    parser.parse_args()
    from .bank import Bank
    Bank(Settings.from_env().database_url).initialize()
    print("UC-04 development schema initialized.")


if __name__ == "__main__":
    main()
