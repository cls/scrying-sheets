import jinja2
import json
import os
import re
import requests
import sys
import time

class Scryfall:
    DEFAULT_HOST = 'https://api.scryfall.com'

    def __init__(self, host=DEFAULT_HOST):
        self._host = host

    def get(self, url, params=None):
        if url.startswith('/'):
            url = self._host + url

        time.sleep(0.1)

        response = requests.get(url, params=params)

        print("GET {}".format(response.url), file=sys.stderr)

        return response

class CardFace:
    def __init__(self, name, url, type_line, mana_cost):
        self.name = name
        self.url = url
        self.type_line = type_line
        self.mana_cost = mana_cost

class Card (CardFace):
    def __init__(self, name, url, type_line, mana_cost, back_faces, tokens):
        super().__init__(name, url, type_line, mana_cost)
        self.back_faces = back_faces
        self.tokens = tokens

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

    def cache(self):
        if self.url:
            return self.url

        self.url = 'img/{}'.format(os.path.basename(self.scryfall_url))

        if not os.path.exists('img'):
            os.mkdir('img')

        with open(self.url, 'wb') as symbol_file:
            symbol_file.write(scryfall.get(self.scryfall_url).content)

scryfall = Scryfall()

loader = jinja2.FileSystemLoader('templates')

env = jinja2.Environment(loader=loader, keep_trailing_newline=True)

template = env.get_template('decklist.html')

card_pattern = re.compile(r'(?P<count>[0-9]+) +(?P<name>[^(]*[^( ])(?: +\((?P<code>[A-Z0-9]+)\)(?: (?P<number>[0-9]+))?)?')

mana_pattern = re.compile(r'\{[^}]+\}')

symbols = {}

for json_entry in scryfall.get('/symbology').json()['data']:
    text = json_entry['symbol']
    scryfall_url = json_entry['svg_uri']
    symbols[text] = Symbol(text, scryfall_url)

def parse_mana(mana_cost_json):
    mana_cost = []
    for mana in mana_pattern.findall(mana_cost_json):
        symbol = symbols[mana]
        symbol.cache()
        mana_cost.append(symbol)
    return mana_cost

cache = {}

def get_card(url, params=None, is_token=False):
    cache_index = (url, tuple(params.items()) if params else ())

    if cache_index in cache:
        return cache[cache_index]

    card_json = scryfall.get(url, params=params).json()

    front_face_json = card_json

    card_url = card_json['scryfall_uri']

    back_faces = []

    if 'card_faces' in card_json:
        front_face_json = card_json['card_faces'][0]
        if card_json['layout'] in ('adventure', 'modal_dfc', 'split'):
            for face_json in card_json['card_faces'][1:]:
                face_name = face_json['name']
                if card_json['layout'] == 'modal_dfc':
                    prefix, query, postfix = card_url.partition('?')
                    face_url = prefix + '?back'
                    if postfix:
                        face_url += '&' + postfix
                else:
                    face_url = card_url
                face_type_line = face_json['type_line']
                face_mana_cost = parse_mana(face_json['mana_cost'])
                face = CardFace(face_name, face_url, face_type_line, face_mana_cost)
                back_faces.append(face)

    card_name = front_face_json['name']

    if card_json['layout'] == 'token':
        card_name += ' Token'

    card_type_line = front_face_json['type_line']
    card_mana_cost = parse_mana(front_face_json['mana_cost'])

    tokens = []

    if not is_token:
        for related_card_json in card_json.get('all_parts', []):
            if related_card_json['component'] == 'token':
                token = get_card(related_card_json['uri'], is_token=True)
                tokens.append((None, token))

    card = Card(card_name, card_url, card_type_line, card_mana_cost, back_faces, tokens)

    cache[cache_index] = card

    return card

def generate_decklist(deck_path):
    sections = []
    section = None
    tokens = Section("Tokens")

    with open(deck_path) as deck_file:
        for deck_line in map(str.strip, deck_file):
            if not deck_line:
                section = None
                continue

            if section is None:
                section = Section(deck_line)
                sections.append(section)
                continue

            match = card_pattern.fullmatch(deck_line)

            name, code, number = cache_index = match.group('name', 'code', 'number')

            if number:
                card = get_card('/cards/{}/{}'.format(code.lower(), number))
            else:
                params = {'exact': name}
                if code:
                    params['set'] = code
                card = get_card('/cards/named', params=params)

            count = int(match.group('count'))

            section.cards.append((count, card))
            tokens.cards.extend(card.tokens)

    if tokens.cards:
        sections.append(tokens)

    title, _ = os.path.splitext(os.path.basename(deck_path))

    title_slug = title.lower().replace(' ', '-')

    html_path = '{}.html'.format(title_slug)

    html = template.render(title=title, sections=sections)

    with open(html_path, 'w') as html_file:
        html_file.write(html)

for deck_path in sys.argv[1:]:
    generate_decklist(deck_path)
