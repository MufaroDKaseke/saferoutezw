"""Create (or reset the password of) a user from the command line.

This is the secure bootstrap for the first administrator: there are no default
credentials. The password is read with a hidden prompt, never from arguments.

    python scripts/create_user.py --email you@example.org --name "Your Name" --role admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import get_session_factory  # noqa: E402
from app.core.security import hash_password, password_policy_problem  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.services.audit import record_audit  # noqa: E402
from app.services.auth import normalise_email, revoke_user_sessions  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="display name")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ADMIN.value)
    parser.add_argument("--reset-password", action="store_true", help="update the password of an existing user")
    args = parser.parse_args(argv)

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    problem = password_policy_problem(password)
    if problem:
        print(problem, file=sys.stderr)
        return 1

    email = normalise_email(args.email)
    with get_session_factory()() as session:
        user = session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and not args.reset_password:
            print("A user with this email already exists (use --reset-password).", file=sys.stderr)
            return 1
        if user is None:
            user = User(email=email, display_name=args.name, role=args.role)
            session.add(user)
            action = "user.created"
        else:
            action = "user.password_reset"
            revoke_user_sessions(session, user.id)
        user.password_hash = hash_password(password)
        session.flush()
        record_audit(session, actor_id=None, action=action, entity_type="user", entity_id=user.id,
                     details={"via": "create_user.py", "role": user.role})
        session.commit()
    print(f"{'Updated' if args.reset_password else 'Created'} {args.role} account for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
