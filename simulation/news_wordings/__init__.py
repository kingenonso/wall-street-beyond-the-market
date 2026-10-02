"""The wordings of the news wire: for every kind of news, three ways of telling it in each newspaper's voice.

`check` proves a set of wordings is sound: every kind and every newspaper is
covered, every wording fills in cleanly from that kind's facts and no others,
and no two wordings are the same.
"""

from __future__ import annotations

import string

from simulation.news_kinds import BY_NAME, OUTLETS

PER_OUTLET = 3
HEADLINE_LIMIT = 110          # characters, once the facts are filled in
BODY_LIMIT = 520


def fields_used(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def check(wordings: dict, kinds: tuple[str, ...]) -> list[str]:
    """Everything wrong with a set of wordings, in plain words. An empty list means it is sound."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for kind in kinds:
        spec = BY_NAME[kind]
        if kind not in wordings:
            problems.append(f"{kind}: no wordings at all")
            continue
        for outlet in OUTLETS:
            options = wordings[kind].get(outlet, [])
            if len(options) < PER_OUTLET:
                problems.append(f"{kind}/{outlet}: {len(options)} wordings, need {PER_OUTLET}")
            for number, option in enumerate(options):
                where = f"{kind}/{outlet}/{number}"
                if len(option) != 2:
                    problems.append(f"{where}: must be a (headline, body) pair")
                    continue
                for part, text, limit in (("headline", option[0], HEADLINE_LIMIT), ("body", option[1], BODY_LIMIT)):
                    unknown = fields_used(text) - set(spec.fields)
                    if unknown:
                        problems.append(f"{where} {part}: uses facts this kind does not have: {sorted(unknown)}")
                        continue
                    filled = text.format(**spec.sample)
                    if len(filled) > limit:
                        problems.append(f"{where} {part}: {len(filled)} characters, limit {limit}")
                    if not filled.strip() or "  " in filled or filled != filled.strip():
                        problems.append(f"{where} {part}: empty, or stray spaces")
                    if text in seen:
                        problems.append(f"{where} {part}: the same words as {seen[text]}")
                    seen[text] = where
                if not fields_used(option[0] + option[1]):
                    problems.append(f"{where}: uses no fact at all")
                if option[0].rstrip().endswith("."):
                    problems.append(f"{where}: a headline does not end with a full stop")
        extra = set(wordings[kind]) - set(OUTLETS)
        if extra:
            problems.append(f"{kind}: unknown newspapers {sorted(extra)}")
    for kind in set(wordings) - set(kinds):
        problems.append(f"{kind}: not one of this file's kinds")
    return problems
