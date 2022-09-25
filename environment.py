import re

import jinja2
import markupsafe


loader = jinja2.FileSystemLoader('templates')

environment = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape(), keep_trailing_newline=True)

korvecdal_pattern = re.compile(r'\b(en|il)-(Kor|Vec|Dal)\b')

@jinja2.pass_eval_context
def filter_korvecdal(eval_ctx, value):
    if eval_ctx.autoescape:
        value = markupsafe.escape(value)
    result = korvecdal_pattern.sub(r'<em>\1</em>-\2', str(value))
    if eval_ctx.autoescape:
        result = markupsafe.Markup(result)
    return result

environment.filters['korvecdal'] = filter_korvecdal
