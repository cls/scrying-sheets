import jinja2
import json
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

class Section:
    def __init__(self, name, cards=None):
        self.name = name
        self.cards = cards or []

    @property
    def total_count(self):
        return sum(count or 0 for count, card in self.cards)

class Symbol:
    def __init__(self, text, scryfall_url):
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

template = env.get_template('decklist.html')

title_pattern = re.compile(r'\((?P<code>[A-Z0-9]+)\) (?P<deck>.*)')
card_pattern = re.compile(r'((?P<count>[0-9]+) +)?(?P<name>[^(]*[^( ])(?: +\((?P<code>[A-Z0-9]+)\)(?: (?P<number>[0-9]+))?)?')
mana_pattern = re.compile(r'\{[^}]+\}')

color_order = ['W', 'U', 'B', 'R', 'G']

symbols = {}

for json_entry in scryfall.get('/symbology').json()['data']:
    text = json_entry['symbol']
    scryfall_url = json_entry['svg_uri']
    symbols[text] = Symbol(text, scryfall_url)

def parse_mana(mana_cost_json):
    mana_cost = []
    for mana in mana_pattern.findall(mana_cost_json):
        symbol = symbols[mana]
        symbol.save()
        mana_cost.append(symbol)
    return mana_cost

cache = {}

def get_card(url, params=None):
    cache_index = (url, tuple(params.items()) if params else ())

    if cache_index in cache:
        return cache[cache_index]

    card_json = scryfall.get(url, params=params).json()

    card_url = card_json['scryfall_uri']

    if 'card_faces' in card_json and card_json['layout'] != 'split':
        front_face_json = card_json['card_faces'][0]
    else:
        front_face_json = card_json

    card_name = front_face_json['name']
    card_type_line = front_face_json['type_line']
    card_mana_cost = parse_mana(front_face_json['mana_cost'])

    card_cmc = card_json['cmc']
    card_colors = card_json['colors']

    card = Card(card_name, card_url, card_type_line, card_mana_cost, card_cmc, card_colors)

    cache[cache_index] = card

    return card

def get_card_sort_key(count_and_card):
    count, card = count_and_card
    return (card.cmc, len(card.colors),list(map(color_order.index, card.colors)), card.name)

def card_sort(sections):
    for section in sections:
        section.cards.sort(key=get_card_sort_key)



sets = {}

def generate_decklist(deck_path):
    title = None
    sections = []
    section = None

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

            if number:
                card = get_card('/cards/{}/{}'.format(code.lower(), number))
                if card.name != name:
                    raise Exception("{} {} has name {!r}, expected {!r}".format(code, number, card.name, name))
            else:
                params = {'exact': name}
                if code:
                    params['set'] = code
                card = get_card('/cards/named', params=params)

            count_str = match.group('count')
            count = int(count_str) if count_str else None

            section.cards.append((count, card))
    # split functions here
    card_sort(sections)
    #
    deck_path_stem, _ = os.path.splitext(os.path.basename(deck_path))

    html_path = '{}.html'.format(deck_path_stem)

    match = title_pattern.fullmatch(title)

    if match:
        deck = match.group('deck')
        code = match.group('code')
        symbol = sets.get(code)
        if not symbol:
            set_json = scryfall.get('/sets/{}'.format(code.lower())).json()
            symbol = Symbol(set_json['name'], set_json['icon_svg_uri'])
            sets[code] = symbol
            symbol.save()
    else:
        deck = title
        code = None
        symbol = None

    html = template.render(title=title, deck=deck, code=code, symbol=symbol, sections=sections)

    with open(html_path, 'w') as html_file:
        html_file.write(html)

for deck_path in sys.argv[1:]:
    generate_decklist(deck_path)
