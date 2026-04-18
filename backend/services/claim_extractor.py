import re
from typing import List


def extract_claims(document: str) -> List[str]:
    """Split document into sentences as individual claims."""
    # Split on sentence-ending punctuation followed by whitespace or end of string
    sentences = re.split(r'(?<=[.!?])\s+', document.strip())
    # Filter out very short or empty fragments
    return [s.strip() for s in sentences if len(s.strip()) > 10]
