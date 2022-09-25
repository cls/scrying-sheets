import sys

from scryfall import Scryfall


scryfall = Scryfall()

basics = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

def rarest_basic(code):
    set_release = None

    def rarity(card_in_set):
        return sum(1 for card in illustrations.get(card_in_set['illustration_id'], []) if card['released_at'] < set_release)

    for name in basics:
        illustrations = {}
        cards_in_set = []

        for card in scryfall.get_list('/cards/search', params={'q': f'!{name!r}', 'unique': 'prints'}):
            if 'illustration_id' not in card:
                continue
            if not card['digital']:
                illustrations.setdefault(card['illustration_id'], []).append(card)
            if card['set'] == code.lower():
                cards_in_set.append(card)
                set_release = card['released_at']

        rarest = min(map(rarity, cards_in_set))

        collector_numbers = " or ".join(card['collector_number'] for card in cards_in_set if rarity(card) == rarest)

        print(f"{name} ({code}) {collector_numbers}")


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        rarest_basic(arg)
