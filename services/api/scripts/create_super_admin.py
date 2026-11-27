"""Create a platform administrator (SUPER_ADMIN). Operator CLI only.

    python -m scripts.create_super_admin "Full Name" person@example.org [--organization-id N] [--another]

There is no public registration and no default password. The account has no
campus and no usable password; a single-use setup link is emailed (SMTP and
FRONTEND_BASE_URL must be configured) and nothing is saved if the email
cannot be sent. Refuses when a SUPER_ADMIN already exists unless --another
is given, and never changes an existing account. Needs migration M1.
"""

import argparse
import sys
from datetime import timedelta

from app.core import email as email_transport
from app.core.config import settings
from app.core.security import PASSWORD_SETUP, create_password_token
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.platform import PlatformAuditLog
from app.models.user import User, UserRole
from app.services.password_management import (
    SETUP_PATH, PasswordLinkConfigError, build_frontend_link, make_unusable_password, setup_email_content,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("full_name")
    parser.add_argument("email")
    parser.add_argument("--organization-id", type=int, default=None,
                        help="limit the account to one organisation (default: every organisation)")
    parser.add_argument("--another", action="store_true", help="allow a further SUPER_ADMIN")
    args = parser.parse_args()
    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print("STOP: this email already belongs to an account.")
            return 1
        if not args.another and db.query(User).filter(User.role == UserRole.SUPER_ADMIN).first():
            print("STOP: a SUPER_ADMIN already exists (use --another to add one).")
            return 1
        if args.organization_id and not db.get(Organization, args.organization_id):
            print("STOP: no such organisation.")
            return 1
        user = User(campus_id=None, organization_id=args.organization_id, full_name=args.full_name.strip(),
                    email=email, password_hash=make_unusable_password(), role=UserRole.SUPER_ADMIN, is_active=True)
        db.add(user)
        db.flush()
        db.add(PlatformAuditLog(actor_user_id=None, actor_email="operator", action="CREATE", target_type="USER",
                                target_id=user.id, outcome="SUCCESS",
                                details={"email": email, "role": "SUPER_ADMIN", "organization_id": args.organization_id,
                                         "provisioned_by": "operator CLI"}))
        token = create_password_token(user.id, user.password_hash, PASSWORD_SETUP,
                                      timedelta(hours=settings.PASSWORD_SETUP_TOKEN_EXPIRE_HOURS))
        link = build_frontend_link(SETUP_PATH, token)
        subject, text, body = setup_email_content(user, None, link)
        email_transport.send_email(user.email, subject, text, body)
        db.commit()
        print(f"Created SUPER_ADMIN #{user.id}; setup link emailed to {email}.")
        return 0
    except (email_transport.EmailDeliveryError, PasswordLinkConfigError) as exc:
        db.rollback()
        print(f"STOP: the setup email could not be sent, so nothing was saved. {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
