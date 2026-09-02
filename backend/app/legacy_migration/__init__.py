"""One-off migration of the desktop SQLite database into PostgreSQL.

Specification: docs/09-data-migration.md. Lives under app/ rather than in the
script so it is covered by mypy and by tests; scripts/migrate_legacy.py is only
the command line around it.
"""
