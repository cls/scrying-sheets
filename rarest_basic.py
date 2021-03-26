import sys

from scryfall import Scryfall

scryfall = Scryfall()

basics = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

for code in sys.argv[1:]:
    released_at = None

    def rarity(card_in_set):
        return sum(1 for card in illustrations.get(card_in_set['illustration_id'], []) if card['released_at'] < set_release)

    for name in basics:
        illustrations = {}
        cards_in_set = []

        for card in scryfall.get_list('/cards/search', params={'q': '!{!r}'.format(name), 'unique': 'prints'}):
            if not card['digital']:
                illustrations.setdefault(card['illustration_id'], []).append(card)
            if card['set'] == code.lower():
                cards_in_set.append(card)
                set_release = card['released_at']

        rarest = min(map(rarity, cards_in_set))

        print("{} ({}) {}".format(name, code, ' or '.join(card['collector_number'] for card in cards_in_set if rarity(card) == rarest)))
