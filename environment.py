import re

import jinja2
import markupsafe


loader = jinja2.FileSystemLoader('templates')

environment = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape(), keep_trailing_newline=True)
