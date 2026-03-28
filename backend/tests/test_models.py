from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, ConnectedAccount, User


def test_user_and_connected_account_roundtrip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="parv@example.com", full_name="Parv")
        session.add(user)
        session.flush()

        account = ConnectedAccount(
            user_id=user.id,
            provider="google",
            provider_account_id="google-oauth-subject-1",
            account_email="parv@gmail.com",
            scopes="gmail.readonly profile email",
        )
        session.add(account)
        session.commit()

    with Session(engine) as session:
        stored_user = session.execute(
            select(User).where(User.email == "parv@example.com")
        ).scalar_one()

        assert stored_user.full_name == "Parv"
        assert len(stored_user.connected_accounts) == 1
        assert stored_user.connected_accounts[0].provider == "google"
