import jinja2
import markupsafe
import os
import re
import sys

from scryfall import Scryfall


class Card:
    def __init__(self, name, url, type_line, mana_cost, cmc, colors):
        self.name = name
        self.url = url
        self.type_line = type_line
        self.mana_cost = mana_cost
        self.cmc = cmc
        self.colors = colors

    @staticmethod
    def from_json(card_json):
        card_url = card_json['scryfall_uri']
        if 'card_faces' in card_json and card_json['layout'] != 'split':
            front_face_json = card_json['card_faces'][0]
        else:
            front_face_json = card_json

        card_name = front_face_json['name']
        card_type_line = front_face_json['type_line']
        card_mana_cost = parse_mana(front_face_json['mana_cost'])

        card_cmc = card_json['cmc']

        # Some cards have two faces and we currently only want the mana from the 'front'
        if 'colors' in card_json:
            card_colors = card_json['colors']
        else:
            card_colors = front_face_json['colors']

        return Card(card_name, card_url, card_type_line, card_mana_cost, card_cmc, card_colors)


class Section:
    def __init__(self, name, cards=None):
        self.name = name
        self.cards = cards or []

    @property
    def total_count(self):
        return sum(count or 0 for count, card in self.cards)


class Symbol:
    def __init__(self, code, text, scryfall_url):
        self.code = code
        self.text = text
        self.scryfall_url = scryfall_url
        self.url = None

    def save(self):
        if self.url:
            return self.url

        self.url = 'img/{}'.format(os.path.basename(self.scryfall_url))

        query_pos = self.url.find('?')
        if query_pos >= 0:
            self.url = self.url[:query_pos]

        if not os.path.exists('img'):
            os.mkdir('img')

        with open(self.url, 'wb') as symbol_file:
            symbol_file.write(scryfall.get(self.scryfall_url).content)

        return self.url


scryfall = Scryfall()

loader = jinja2.FileSystemLoader('templates')

env = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape(), keep_trailing_newline=True)

title_pattern = re.compile(r'\((?P<code>[A-Z0-9]+)\) (?P<deck>.*)')
card_pattern = re.compile(r'((?P<count>[0-9]+) +)?(?P<name>[^(]*[^( ])(?: +\((?P<code>[A-Z0-9]+)\)(?: (?P<number>[0-9]+))?)?')
mana_pattern = re.compile(r'\{[^}]+\}')
korvecdal_pattern = re.compile(r'\b(en|il)-(Kor|Vec|Dal)\b')

@jinja2.pass_eval_context
def korvecdal(eval_ctx, value):
    if eval_ctx.autoescape:
        value = markupsafe.escape(value)
    result = korvecdal_pattern.sub(r'<em>\1</em>-\2', str(value))
    if eval_ctx.autoescape:
        result = markupsafe.Markup(result)
    return result

env.filters['korvecdal'] = korvecdal

template = env.get_template('decklist.html')

color_order = ['W', 'U', 'B', 'R', 'G']

symbols = {}

def parse_mana(mana_cost_json):
    mana_cost = []
    for mana in mana_pattern.findall(mana_cost_json):
        # If we don't know this mana symbol then we must not have fetched /symbology yet.
        if mana not in symbols:
            for symbol_json in scryfall.get_list('/symbology'):
                if symbol_json['represents_mana']:
                    code = symbol_json['symbol']
                    symbols[code] = Symbol(code, symbol_json['english'], symbol_json['svg_uri'])
        # If we still don't know the mana symbol then we'll raise an exception.
        symbol = symbols[mana]
        symbol.save()
        mana_cost.append(symbol)
    return mana_cost

def get_card_sort_key(count_and_card):
    count, card = count_and_card
    return (card.cmc, len(card.colors), list(map(color_order.index, card.colors)), card.name)

def card_sort(sections):
    for section in sections:
        section.cards.sort(key=get_card_sort_key)

# This function gets the deck list as a set of cards, rather than fetching each card individually
def fetch_collection(identifiers):
    post_json = {"identifiers": identifiers}

    collection_json = scryfall.post('/cards/collection/', post_json).json()

    if collection_json['not_found']:
        raise Exception("Could not find cards: {}".format(collection_json['not_found']))

    return list(map(Card.from_json, collection_json['data']))

sets = {}

def generate_decklist(deck_path):
    title = None
    sections = []
    section = None

    identifiers = []

    with open(deck_path) as deck_file:
        for line in map(str.strip, deck_file):
            if not line:
                section = None
                continue

            if not title:
                title = line
                continue

            if section is None:
                section = Section(line)
                sections.append(section)
                continue

            match = card_pattern.fullmatch(line)

            name, code, number = cache_index = match.group('name', 'code', 'number')
            count_str = match.group('count')
            count = int(count_str) if count_str else None

            # Leave index as a placeholder that we later use to obtain the card.
            index = len(identifiers)
            section.cards.append((count, index))

            identifier = {}

            if number:
                identifier['collector_number'] = number
                identifier['set'] = code.lower()
            else:
                # /cards/collection apparently can't identify split cards by
                # their full name (e.g. Fire // Ice), so instead we use only
                # their first name (e.g. Fire), which is still unique.
                identifier['name'] = name.split('//')[0].strip()
                if code:
                    identifier['set'] = code

            identifiers.append(identifier)

    # Using the identifiers, get the cards from scryfall and unpack them
    # However, /cards/collection only fetches up to 75 cards at a time
    collection = []
    for i in range(0, len(identifiers), 75):
        collection.extend(fetch_collection(identifiers[i:i+75]))

    for section in sections:
        section.cards = [(count, collection[index]) for count, index in section.cards]

    # Sort the deck list by cmc, WUBRG, number of colours, alphabetical
    card_sort(sections)

    deck_path_stem, _ = os.path.splitext(os.path.basename(deck_path))

    html_path = '{}.html'.format(deck_path_stem)

    match = title_pattern.fullmatch(title)

    if match:
        deck = match.group('deck')
        code = match.group('code').lower()
        symbol = sets.get(code)
        if not symbol:
            set_json = scryfall.get('/sets/{}'.format(code)).json()
            symbol = Symbol(set_json['code'].upper(), set_json['name'], set_json['icon_svg_uri'])
            sets[code] = symbol
            symbol.save()
    else:
        deck = title
        symbol = None

    html = template.render(title=title, deck=deck, symbol=symbol, sections=sections)

    with open(html_path, 'w') as html_file:
        html_file.write(html)


if __name__ == '__main__':
    for deck_path in sys.argv[1:]:
        print("Generating {}".format(deck_path), file=sys.stderr)
        generate_decklist(deck_path)
