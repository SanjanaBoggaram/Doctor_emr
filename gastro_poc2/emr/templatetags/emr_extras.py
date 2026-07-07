from django import template

register = template.Library()


@register.filter
def lines(value):
    """Join a list into newline-separated text for <textarea> display.

    Avoids the broken ``{{ list|join:"\\n" }}`` idiom: a Django variable tag
    can't span a literal newline, and a "\\n" filter argument is treated as a
    literal backslash-n rather than a newline.
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return "\n".join(str(x) for x in value)
