"""add search_vector tsvector column to emails

Revision ID: 20260318_0003
Revises: 20260318_0002
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260318_0003"
down_revision = "20260318_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tsvector column for full-text search
    op.execute(
        """
        ALTER TABLE emails
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        """
    )

    # Create GIN index for fast full-text search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_emails_search_vector
        ON emails USING GIN (search_vector)
        """
    )

    # Populate existing rows
    op.execute(
        """
        UPDATE emails SET search_vector =
            setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(from_name, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(from_address, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(snippet, '')), 'C') ||
            setweight(to_tsvector('english', coalesce(body_text, '')), 'D')
        """
    )

    # Create trigger function to auto-update search_vector on INSERT/UPDATE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION emails_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.subject, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.from_name, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.from_address, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.snippet, '')), 'C') ||
                setweight(to_tsvector('english', coalesce(NEW.body_text, '')), 'D');
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS emails_search_vector_trigger ON emails;
        CREATE TRIGGER emails_search_vector_trigger
        BEFORE INSERT OR UPDATE OF subject, from_name, from_address, snippet, body_text
        ON emails
        FOR EACH ROW
        EXECUTE FUNCTION emails_search_vector_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS emails_search_vector_trigger ON emails")
    op.execute("DROP FUNCTION IF EXISTS emails_search_vector_update()")
    op.execute("DROP INDEX IF EXISTS ix_emails_search_vector")
    op.execute("ALTER TABLE emails DROP COLUMN IF EXISTS search_vector")
