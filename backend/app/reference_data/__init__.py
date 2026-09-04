"""Reference data: countries, denomination units and materials.

Pure data and pure functions — nothing here imports SQLAlchemy or touches a
session. That is deliberate: migration 0003 turns the legacy strings into this
structure, and a migration that imports ORM models breaks the moment the models
move on. Tests exercise the parsers directly.
"""
