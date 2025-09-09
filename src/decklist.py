import os
import re
import sys
from typing import Any

from environment import environment
from scry import Card, Set


class Section:
    def __init__(self, name, cards=None):
        self.name = name
        self.cards = cards or {}

    @property
    def total_count(self):
        return sum(self.cards.values())


title_pattern = re.compile(r"\((?P<code>[A-Z0-9]+)\) (?P<deck>.*)")
card_pattern = re.compile(
    r"((?P<count>[0-9]+) +)?(?P<name>[^(]*[^( ])(?: +\((?P<code>[A-Z0-9]+)\)(?: (?P<number>[0-9]+[a-z]?))?)?"
)

template = environment.get_template("decklist.html")

set_symbols: dict[str, Set] = {}

Placeholder = tuple[tuple[str, Any], ...]


def frozendict(d):
    return tuple(sorted(d.items()))


def parse_decklist(deck_path, placeholders):
    title = None
    sections = []
    section = None

    with open(deck_path, encoding="utf-8") as deck_file:
        for line in map(str.strip, deck_file):
            if not line:
                section = None
                continue

            if not title:
                title = line
                continue

            if not section:
                section = Section(line)
                sections.append(section)
                continue

            match = card_pattern.fullmatch(line)
            if not match:
                raise Exception(f"Failed to parse line: {line!r}")

            name, code, number = match.group("name", "code", "number")
            count_str = match.group("count")
            count = int(count_str) if count_str else 0

            identifier = {}

            if number:
                identifier["collector_number"] = number
            else:
                # /cards/collection apparently can't identify split cards by
                # their full name (e.g. Fire // Ice), so instead we use only
                # their first name (e.g. Fire), which is still unique.
                identifier["name"] = name.split("//")[0].strip()

            if code:
                identifier["set"] = code

            # Leave identifier as a placeholder that we later use to obtain the card.
            placeholder = frozendict(identifier)
            section.cards[placeholder] = count
            placeholders.add(placeholder)

    return title, sections


def fetch_collection(placeholders):
    identifiers = list(map(dict, placeholders))

    cards = Card.collection(identifiers)

    return dict(zip(placeholders, cards))


def pluralize(word):
    return f"{word[:-1]}ies" if word[-1] == "y" else f"{word}s"


def generate_html(deck_path, decklist, collection):
    title, sections = decklist

    deck_path_stem, _ = os.path.splitext(os.path.basename(deck_path))
    html_path = f"{deck_path_stem}.html"
    print(f"Generating {html_path}")

    for section in sections:
        section.cards = {
            collection[placeholder]: count
            for placeholder, count in section.cards.items()
        }

    commanders = None
    maindeck_index = None
    maindeck_sections = []

    for i, section in enumerate(sections):
        if section.name == "Commander":
            commanders = section.total_count

        elif section.name == "Deck":
            if maindeck_index is not None:
                raise Exception(f"{deck_path} contains more than one 'Deck' section")
            maindeck_index = i

            if commanders is None:
                format_minima = (
                    40,  # Limited
                    60,  # Constructed
                    80,  # Constructed with Yorion
                )
                if section.total_count not in format_minima:
                    print(
                        f"Warning: {deck_path} maindeck contains {section.total_count} cards",
                        file=sys.stderr,
                    )
            else:
                if section.total_count + commanders != 100:
                    print(
                        f"Warning: {deck_path} maindeck contains {section.total_count} + {commanders} cards",
                        file=sys.stderr,
                    )

            categories = [
                ("Land",),
                ("Creature",),
                ("Planeswalker",),
                ("Instant", "Sorcery"),
                ("Artifact", "Enchantment"),
                ("Battle",),
            ]
            # Land is treated specially: it is the first filtered, yet the last rendered.
            rendered_categories = categories[1:] + categories[:1]

            cards_by_category = {category: {} for category in categories}
            types_by_category = {category: set() for category in categories}

            for card, count in section.cards.items():
                for category in categories:
                    card_types = set(
                        filter(card.front.type_line.__contains__, category)
                    )
                    if card_types:
                        cards_by_category[category][card] = count
                        types_by_category[category].update(card_types)
                        break
                else:
                    raise Exception(f"Unrecognized card type line {card.type_line}")

            for category in rendered_categories:
                cards_in_category = cards_by_category[category]
                if cards_in_category:
                    types_in_category = types_by_category[category]
                    category_words = filter(types_in_category.__contains__, category)
                    if len(cards_in_category) == 1:
                        singular = next(iter(cards_in_category.values())) == 1
                    else:
                        singular = False
                    if not singular:
                        category_words = map(pluralize, category_words)
                    new_section = Section(" & ".join(category_words), cards_in_category)
                    maindeck_sections.append(new_section)

        elif section.name == "Sideboard":
            if section.total_count not in (0, 15):
                print(
                    f"Warning: {deck_path} sideboard contains {section.total_count} cards",
                    file=sys.stderr,
                )

    if maindeck_index is not None:
        sections[maindeck_index : maindeck_index + 1] = maindeck_sections

    match = title_pattern.fullmatch(title)

    if match:
        deck = match.group("deck")
        code = match.group("code").lower()
        global set_symbols
        if code not in set_symbols:
            set_symbols = {symbol.code: symbol for symbol in Set.list()}
        symbol = set_symbols[code]
    else:
        deck = title
        symbol = None

    html = template.render(title=title, deck=deck, set=symbol, sections=sections)

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html)


if __name__ == "__main__":
    decklists = {}
    placeholders: set[Placeholder] = set()

    for path in sys.argv[1:]:
        decklist = parse_decklist(path, placeholders)
        decklists[path] = decklist

    collection = fetch_collection(placeholders)

    for path, decklist in decklists.items():
        generate_html(path, decklist, collection)
