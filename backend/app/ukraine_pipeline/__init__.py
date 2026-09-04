"""The Ukrainian pipeline (stage 4.5, part B).

Where the reconnaissance in app/ukraine_recon/ only looked, this package
writes: it links our catalogue to the three Ukrainian sources, fills the gaps,
takes the official names and photos from the National Bank, renames the series
to the NBU canon and records one price snapshot per linked coin.

The parsers are the reconnaissance ones — this package is the decisions on top
of them. Every step is separately runnable, idempotent, and reports what it
did rather than changing the database quietly.
"""
