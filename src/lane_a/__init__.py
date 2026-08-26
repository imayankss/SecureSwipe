"""Lane A (IEEE-CIS) support code.

Deliberately isolated from Lane B. Nothing in this package imports
``src.preprocessing.feature_config``; the Lane A feature space is disjoint from
the Lane B ``ALL_FEATURES`` contract and the two must never be merged, aligned,
or renamed into one another.
"""
