import math
import os
import re
import requests
import sys
import time

from functools import total_ordering


class Scry:
    API = 'https://api.scryfall.com'

    def __init__(self, uri):
        self.uri = Scry.API + uri if uri.startswith('/') else uri

    def __str__(self):
        return self.uri

    def __repr__(self):
        return f'Scry({self.uri!r})'

    def get(self, **kwargs):
        if self.uri.startswith(Scry.API):
            time.sleep(0.1)
        response = requests.get(self.uri, params=kwargs)
        print(f"GET {response.url}", file=sys.stderr)
        response.raise_for_status() # raise if not 200 OK
        return response

    def post(self, **kwargs):
        if self.uri.startswith(Scry.API):
            time.sleep(0.1)
        response = requests.post(self.uri, json=kwargs)
        print(f"POST {response.url}", file=sys.stderr)
        response.raise_for_status() # raise if not 200 OK
        return response


class Object:
    _subclasses = {}

    def __init_subclass__(cls, /, object, **kwargs):
        super().__init_subclass__(**kwargs)
        Object._subclasses[object] = cls
        cls.object = object

    def __new__(cls, json):
        return super().__new__(Object._subclasses[json['object']] if cls is Object else cls)

    def __init__(self, json):
        if json['object'] != self.object:
            raise Exception(f"Creating {type(self)} from json object {json.get('object')!r}")
        self._json = json
        self.__dict__.update(Object._map(json))

    def __str__(self):
        return str(self._json)

    def __repr__(self):
        return f'Object({self._json!r})'

    @staticmethod
    def get(uri, **kwargs):
        return Object(Scry(uri).get(**kwargs).json())

    @staticmethod
    def post(uri, **kwargs):
        return Object(Scry(uri).post(**kwargs).json())

    @staticmethod
    def _map(json):
        if isinstance(json, dict):
            return {k: Object._submap(v) for k, v in json.items()}
        elif isinstance(json, list):
            return [Object._submap(v) for v in json]
        return json

    @staticmethod
    def _submap(json):
        return Object(json) if isinstance(json, dict) and 'object' in json else Object._map(json)

    def _store(self, name):
        uri = getattr(self, name)
        basename = os.path.basename(str(uri))

        path = f'img/{basename}'
        query_pos = path.find('?')
        if query_pos >= 0:
            path = path[:query_pos]

        if not os.path.exists('img'):
            os.mkdir('img')

        if not os.path.exists(path):
            image_data = uri.get().content

            with open(path, 'wb') as image_file:
                image_file.write(image_data)

        return path


class Error(Object, object='error'):
    pass


class List(Object, object='list'):
    def __iter__(self):
        return List.Iter(self)

    def __len__(self):
        return self.total_cards

    class Iter:
        def __init__(self, page):
            self._page = page
            self._iter = iter(page.data)

        def __iter__(self):
            return self

        def __next__(self):
            try:
                return next(self._iter)
            except StopIteration as e:
                if not self._page.has_more:
                    raise e
                self._page = self._page.next_page()
                self._iter = iter(self._page.data)
                return next(self)


class Set(Object, object='set'):
    def __init__(self, json):
        super().__init__(json)
        if 'scryfall_uri' in json:
            self.scryfall_uri = Scry(json['scryfall_uri'])
        if 'icon_svg_uri' in json:
            self.icon_svg_uri = Scry(json['icon_svg_uri'])
        if 'search_uri' in json:
            self.search_uri = Scry(json['search_uri'])

    def icon_svg(self):
        return self._store('icon_svg_uri')

    @staticmethod
    def list(**kwargs):
        return Object.get('/sets', **kwargs)

    @staticmethod
    def from_code(code, **kwargs):
        return Object.get(f'/sets/{code}', **kwargs)

    @staticmethod
    def from_tcgplayer_id(tcgplayer_id, **kwargs):
        return Object.get(f'/sets/tcgplayer/{tcgplayer_id}', **kwargs)

    @staticmethod
    def from_id(id, **kwargs):
        return Object.get(f'/sets/{id}', **kwargs)


class Card(Object, object='card'):
    def __init__(self, json):
        super().__init__(json)
        if 'colors' in json:
            self.colors = list(map(Color, json['colors']))
        if 'mana_cost' in json:
            self.mana = Mana(json['mana_cost'])
        if 'prints_search_uri' in json:
            self.prints_search_uri = Scry(json['prints_search_uri'])
        if 'rulings_uri' in json:
            self.rulings_uri = Scry(json['rulings_uri'])
        if 'scryfall_uri' in json:
            self.scryfall_uri = Scry(json['scryfall_uri'])

    @property
    def cmc_or_inf(self):
        return self.cmc if self.front.mana.symbols else math.inf

    @property
    def frame_rank(self):
        # Frame rank represents the general card categorisation within sets:
        #  0. Colorless
        #  1. White
        #  2. Blue
        #  3. Black
        #  4. Red
        #  5. Green
        #  6. Multicolored
        #  7. Colorless artifact
        #  8. Land
        #  9. Emblem
        # 10. Card
        if self.front.type_line in ('Card', 'Dungeon'):
            return 10
        elif 'Emblem' in self.front.type_line:
            return 9
        elif 'Land' in self.front.type_line:
            return 8
        # Adventures are multi-faced but their faces have no recorded color.
        # However, we can't check for layout == 'adventure' because then any
        # future heterochromatic Adventure would break. It's not pretty, but
        # let's use the front's color if it exists and the card's otherwise.
        colors = self.front.colors if hasattr(self.front, 'colors') else self.colors
        if len(colors) == 1:
            return colors[0].rank + 1
        elif len(colors) > 1:
            return 6
        elif 'Artifact' in self.front.type_line:
            return 7
        else:
            return 0

    @property
    def front(self):
        return self.card_faces[0] if 'card_faces' in self._json and self.layout != 'split' else self

    @staticmethod
    def search(q, **kwargs):
        return Object.get('/cards/search', q=q, **kwargs)

    @staticmethod
    def named(**kwargs):
        return Object.get('/cards/named', **kwargs)

    @staticmethod
    def autocomplete(q, **kwargs):
        return Object.get('/cards/autocomplete', q=q, **kwargs)

    @staticmethod
    def random(q=None, **kwargs):
        return Object.get('/cards/random', q=q, **kwargs)

    @staticmethod
    def collection(identifiers, **kwargs):
        card_limit = 75
        this_page = identifiers[:card_limit]
        next_page = identifiers[card_limit:]
        collection = Object.post('/cards/collection', identifiers=this_page, **kwargs)
        # Collections aren't quite like normal lists, as they lack 'has_next'
        # and hence 'next_page', so we stitch our own onto the returned object.
        if collection.not_found:
            raise Exception(f"Not found: {collection.not_found}")
        has_more = bool(next_page)
        collection.has_more = has_more
        if has_more:
            collection.next_page = lambda: Card.collection(next_page, **kwargs)
        return collection

    @staticmethod
    def from_collector_number(code, number, lang=None, **kwargs):
        uri = f'/cards/{code}/{number}'
        if lang:
            uri += f'/{lang}'
        return Scry(uri).get(kwargs)

    @staticmethod
    def from_multiverse_id(multiverse_id, **kwargs):
        return Object.get(f'/cards/multiverse/{multiverse_id}', **kwargs)

    @staticmethod
    def from_mtgo_id(mtgo_id, **kwargs):
        return Object.get(f'/cards/mtgo/{mtgo_id}', **kwargs)

    @staticmethod
    def from_arena_id(arena_id, **kwargs):
        return Object.get(f'/cards/arena/{arena_id}', **kwargs)

    @staticmethod
    def from_tcgplayer_id(tcgplayer_id, **kwargs):
        return Object.get(f'/cards/tcgplayer/{tcgplayer_id}', **kwargs)

    @staticmethod
    def from_cardmarket_id(cardmarket_id, **kwargs):
        return Object.get(f'/cards/cardmarket/{cardmarket_id}', **kwargs)

    @staticmethod
    def from_id(id, **kwargs):
        return Object.get(f'/cards/{id}', **kwargs)


class CardFace(Object, object='card_face'):
    def __init__(self, json):
        super().__init__(json)
        if 'colors' in json:
            self.colors = list(map(Color, json['colors']))
        if 'mana_cost' in json:
            self.mana = Mana(json['mana_cost'])


class RelatedCard(Object, object='related_card'):
    pass


class Ruling(Object, object='ruling'):
    @staticmethod
    def by_multiverse_id(multiverse_id, **kwargs):
        return Object.get(f'/cards/multiverse/{multiverse_id}/rulings', **kwargs)

    @staticmethod
    def by_mtgo_id(mtgo_id, **kwargs):
        return Object.get(f'/cards/mtgo/{mtgo_id}', **kwargs)

    @staticmethod
    def by_arena_id(arena_id, **kwargs):
        return Object.get(f'/cards/arena/{arena_id}', **kwargs)

    @staticmethod
    def by_collector_number(code, number, **kwargs):
        return Object.get(f'/cards/{code}/{number}', **kwargs)

    @staticmethod
    def by_id(id, **kwargs):
        return Object.get(f'/cards/{id}', **kwargs)


class CardSymbol(Object, object='card_symbol'):
    def __init__(self, json):
        super().__init__(json)
        if 'svg_uri' in json:
            self.svg_uri = Scry(json['svg_uri'])

    def svg(self):
        return self._store('svg_uri')

    @staticmethod
    def list(**kwargs):
        return Object.get('/symbology', **kwargs)


@total_ordering
class Color:
    def __init__(self, code):
        self._code = code

    def __str__(self):
        return self._code

    def __eq__(self, other):
        return self._code == other._code

    def __lt__(self, other):
        return self.rank < other.rank

    @property
    def rank(self):
        return 'WUBRG'.index(self._code)

    def __hash__(self):
        return hash(self._code)


class Mana:
    _pattern = re.compile(r'\{[^}]+\}')
    _symbols = None

    def __init__(self, cost):
        self.cost = cost
        if Mana._symbols is None:
            Mana._symbols = {symbol.symbol: symbol for symbol in CardSymbol.list() if symbol.represents_mana}
        self.symbols = []
        self.cmc = 0
        colors = set()
        for code in Mana._pattern.findall(cost):
            symbol = Mana._symbols[code]
            self.symbols.append(symbol)
            self.cmc += symbol.cmc
            colors.update(map(Color, symbol.colors))
        self.colors = list(colors)

    def __iter__(self):
        return iter(self.symbols)

    @property
    def colorless(self):
        return len(self.colors) == 0

    @property
    def monocolored(self):
        return len(self.colors) == 1

    @property
    def multicolored(self):
        return len(self.colors) >= 2


class ManaCost(Object, object='mana_cost'):
    @staticmethod
    def parse(cost, **kwargs):
        return Object.get('/symbology/parse-mana', cost=cost, **kwargs)


class Catalog(Object, object='catalog'):
    @staticmethod
    def card_names(**kwargs):
        return Object.get('/catalog/card-names', **kwargs)

    @staticmethod
    def artist_names(**kwargs):
        return Object.get('/catalog/artist-names', **kwargs)

    @staticmethod
    def word_bank(**kwargs):
        return Object.get('/catalog/word-bank', **kwargs)

    @staticmethod
    def creature_types(**kwargs):
        return Object.get('/catalog/creature-types', **kwargs)

    @staticmethod
    def planeswalker_types(**kwargs):
        return Object.get('/catalog/planeswalker-types', **kwargs)

    @staticmethod
    def land_types(**kwargs):
        return Object.get('/catalog/land-types', **kwargs)

    @staticmethod
    def artifact_types(**kwargs):
        return Object.get('/catalog/artifact-types', **kwargs)

    @staticmethod
    def enchantment_types(**kwargs):
        return Object.get('/catalog/enchantment-types', **kwargs)

    @staticmethod
    def spell_types(**kwargs):
        return Object.get('/catalog/spell-types', **kwargs)

    @staticmethod
    def powers(**kwargs):
        return Object.get('/catalog/powers', **kwargs)

    @staticmethod
    def toughnesses(**kwargs):
        return Object.get('/catalog/toughnesses', **kwargs)

    @staticmethod
    def loyalties(**kwargs):
        return Object.get('/catalog/loyalties', **kwargs)

    @staticmethod
    def watermarks(**kwargs):
        return Object.get('/catalog/watermarks', **kwargs)

    @staticmethod
    def keyword_abilities(**kwargs):
        return Object.get('/catalog/keyword-abilities', **kwargs)

    @staticmethod
    def keyword_actions(**kwargs):
        return Object.get('/catalog/keyword-actions', **kwargs)

    @staticmethod
    def ability_words(**kwargs):
        return Object.get('/catalog/ability-words', **kwargs)


class BulkData(Object, object='bulk_data'):
    @staticmethod
    def list(**kwargs):
        return Object.get('/bulk-data', **kwargs)

    @staticmethod
    def from_id(id):
        return Object.get('f/bulk-data/{id}', **kwargs)

    @staticmethod
    def from_type(type):
        return Object.get('f/bulk-data/{type}', **kwargs)


class Migration(Object, object='migration'):
    @staticmethod
    def list(**kwargs):
        return Object.get('/migrations', **kwargs)

    @staticmethod
    def from_id(id, **kwargs):
        return Object.get(f'/migrations/{id}', **kwargs)
