"""Local SRT normalization; no translation service dependency."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SubtitleBlock:
    number: str
    timing: str
    text: str


def duration_seconds(timing):
    match = re.fullmatch(
        r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> '
        r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3})(?: .*)?', timing)
    if match is None:
        raise ValueError(f'Hibás SRT időzítés: {timing}')
    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
    duration_ms = ((h2 - h1) * 3600 + (m2 - m1) * 60 + s2 - s1) * 1000 + ms2 - ms1
    if duration_ms <= 0:
        raise ValueError(f'A megjelenési idő nem pozitív: {timing}')
    return duration_ms / 1000


def parse_subtitle(text, *, allow_empty=False, allow_empty_blocks=False):
    """SRT szöveg ellenőrzése és blokkokra bontása, a szövegsorok megőrzésével."""
    text = text.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        if allow_empty:
            return []
        raise ValueError('A felirat üres.')
    if re.search(r'^\s*```', text, re.M):
        raise ValueError('Markdown-kódkeret helyett SRT szükséges.')
    blocks = []
    for raw in re.split(r'\n[ \t]*\n', text):
        lines = raw.splitlines()
        if (len(lines) < (2 if allow_empty_blocks else 3) or not lines[0].isdigit() or
                not re.fullmatch(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}(?: .*)?', lines[1])):
            raise ValueError(f'Hibás SRT blokk: {len(blocks) + 1}')
        duration_seconds(lines[1])
        blocks.append(SubtitleBlock(lines[0], lines[1], '\n'.join(lines[2:])))
    return blocks

def format_subtitle(blocks):
    return '\n\n'.join(f'{b.number}\n{b.timing}\n{b.text}' for b in blocks)
