"""Grant or revoke the admin role for an already registered user.

The second administrator registers through the normal form — that is a
deliberate test of the new-user path — and only then gets the role here.
See docs/09-data-migration.md.

    python scripts/promote_admin.py --email <admin-email>
    python scripts/promote_admin.py --email <admin-email> --demote

The address is always an argument: no email is ever hardcoded (the repository
is public).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_session_factory
from app.models import AuditLog, User
from app.models.enums import UserRole

EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_NOT_VERIFIED = 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grant or revoke the admin role.")
    parser.add_argument("--email", required=True, help="address of a registered user")
    parser.add_argument(
        "--demote",
        action="store_true",
        help="revoke the admin role instead of granting it",
    )
    return parser.parse_args(argv)


async def _apply(session: AsyncSession, email: str, *, demote: bool) -> int:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        print(f"No user found for {email}", file=sys.stderr)
        return EXIT_NOT_FOUND

    # An unverified account means registration was never finished; granting the
    # role now would hand admin rights to an unconfirmed address.
    if not user.email_verified and not demote:
        print(
            f"User {email} has not confirmed their email address yet; finish registration first.",
            file=sys.stderr,
        )
        return EXIT_NOT_VERIFIED

    target = UserRole.USER if demote else UserRole.ADMIN
    if user.role == target:
        print(f"User {email} already has role '{target.value}', nothing to do.")
        return EXIT_OK

    previous = user.role
    user.role = target
    session.add(
        AuditLog(
            user_id=user.id,
            action="role.demote" if demote else "role.promote",
            entity_type="user",
            entity_id=str(user.id),
            details={"from": previous.value, "to": target.value},
        )
    )
    await session.commit()
    print(f"User {email}: role {previous.value} -> {target.value}")
    return EXIT_OK


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        async with get_session_factory()() as session:
            return await _apply(session, args.email, demote=args.demote)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
