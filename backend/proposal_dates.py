"""Abstain when a model supplies precision absent from its cited deadline."""
import re


def supported_candidate(quote, due_at):
    if not due_at:
        return None
    has_year = re.search(r'\b(?:19|20|21)\d{2}\b', quote)
    has_time = re.search(r'\b\d{1,2}:\d{2}\b|T\d{2}:\d{2}|\b\d{1,2}\s*(?:am|pm)\b', quote, re.I)
    has_zone = re.search(r'\b(?:UTC|GMT|IST|PST|PDT|EST|EDT|CST|CDT|MST|MDT|CET|CEST|BST|JST|AEST|AEDT)\b|[+-]\d{2}:?\d{2}\b|T\d{2}:\d{2}(?::\d{2})?Z\b', quote, re.I)
    # This checks explicit precision, not correct date interpretation. Confirmation remains human.
    return due_at if has_year and has_time and has_zone else None
