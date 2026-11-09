"""Select the actual page identity of a controlled, fresh Chrome session."""
import re


def controlled_page_id(listing_text):
    assert isinstance(listing_text, str), 'Page listing must be text'
    assert listing_text.count('## Pages\n') == 1, 'Missing/ambiguous native page listing'
    section = listing_text.split('## Pages\n', 1)[1].split('\n## ', 1)[0]
    rows = [line.strip() for line in section.splitlines() if line.strip()]
    assert len(rows) == 1, 'Controlled session must contain exactly one initial page'
    match = re.fullmatch(r'([0-9]+): about:blank(?: \[selected\])?', rows[0])
    assert match, 'Initial page is not the controlled about:blank target'
    return int(match[1])
