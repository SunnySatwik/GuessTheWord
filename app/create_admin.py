"""CLI entry point for controlled Admin account provisioning.

Usage:
    python -m app.create_admin
"""

import getpass
import sys
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.auth_service import create_admin_account


def run_create_admin(
    db: Session | None = None,
    username_input: str | None = None,
    password_input: str | None = None,
    confirm_input: str | None = None,
) -> int:
    """Run admin account provisioning CLI.

    Can be invoked interactively or with explicit inputs for automated testing.
    Returns 0 on success, 1 on failure.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        if username_input is None:
            username = input("Enter admin username: ").strip()
        else:
            username = username_input.strip()

        if password_input is None:
            password = getpass.getpass("Enter admin password: ")
        else:
            password = password_input

        if confirm_input is None:
            confirm = getpass.getpass("Confirm admin password: ")
        else:
            confirm = confirm_input

        admin = create_admin_account(
            db=db,
            username=username,
            password=password,
            confirm_password=confirm,
        )
        print(f"Success: Admin account '{admin.username}' created successfully.")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Failed to create admin account: {e}", file=sys.stderr)
        return 1
    finally:
        if close_db:
            db.close()


def main() -> None:
    exit_code = run_create_admin()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
