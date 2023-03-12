import sys

from scryfall import Scryfall


scryfall = Scryfall()

basics = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']

def rarest_basic(code):
    set_release = None

    def get_rarity(card_in_set):
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

        by_rarity = sorted((get_rarity(card), card['collector_number']) for card in cards_in_set)

        print(f"{name} ({code.upper()})", end='')

        sep = ":"
        for rarity, number in by_rarity:
            print(f"{sep} {number} ({rarity})", end='')
            sep = ","
        print()


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        rarest_basic(arg)
