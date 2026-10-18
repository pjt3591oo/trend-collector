"""Shared keyword matching without collection dependencies."""
import re

def term_pattern(term):
    # ASCII token boundaries avoid matching AI in "said" or app in "happy",
    # while allowing Korean suffixes such as "AI가".
    escaped = re.escape(term)
    if term[0].isascii() and term[0].isalnum():
        escaped = r'(?<![a-z0-9])' + escaped
    if term[-1].isascii() and term[-1].isalnum():
        escaped += r'(?![a-z0-9])'
    return re.compile(escaped, re.I)

