"""Reconnaissance of the Ukrainian coin sources (stage 4.5, part A).

Read-only parsers for the three sources that describe the same coins from
three angles: the National Bank of Ukraine (the issuer), ua-coins.info (a
structured secondary catalogue with prices) and the Ukrainian Wikipedia lists
(numbered, volunteer-maintained). Part B, the pipeline itself, is meant to
reuse these parsers; the script in scripts/recon_ukraine.py is only the
command line around them.

Nothing in this package writes to the database or to object storage.
"""
