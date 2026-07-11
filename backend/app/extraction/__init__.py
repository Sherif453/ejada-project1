"""Extraction package.

The backend calls `extract_document` from `pipeline.py`.
The extraction implementation can change internally without touching the API or
database code as long as it keeps the `extract_document` contract.
"""
