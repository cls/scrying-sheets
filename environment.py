import re

import jinja2
import markupsafe

from scry import CardSymbol


loader = jinja2.FileSystemLoader('templates')

environment = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape(), keep_trailing_newline=True)

mana_pattern = re.compile(r'\{[^}]+\}')
mana_symbols = []

def filter_mana_symbols(string):
    for code in mana_pattern.findall(string):
        # If we don't know this mana symbol then we must not have fetched /symbology yet.
        global mana_symbols
        if code not in mana_symbols:
            mana_symbols = {symbol.symbol: symbol for symbol in CardSymbol.list() if symbol.represents_mana}
        # If we still don't know the mana symbol then we'll raise an exception.
        symbol = mana_symbols[code]
        symbol.store_svg()
        yield symbol

environment.filters['mana_symbols'] = filter_mana_symbols
