"""Text cards: one transparent PNG per sentence, drawn at final video size."""
from PIL import Image, ImageDraw, ImageFont

from .paths import FONTS

DEFAULT_STYLE = {
    "blur": 0,              # background blur strength, 0-40
    "dim": 0,               # darken the background, percent 0-80
    "position": 50,         # vertical centre of the text, percent from the top
    "width": 86,            # max card/text width, percent of video width
    "text_color": "#f0f0f0",
    "font_size": 64,        # px at 1080 wide
    "bold": False,
    "outline": False,       # stroke around letters, for text without a card
    "outline_color": "#000000",
    "card": True,
    "card_color": "#212124",
    "card_opacity": 100,    # percent
}

_LIMITS = {"blur": (0, 40), "dim": (0, 80), "position": (5, 95), "width": (40, 96),
           "font_size": (28, 140), "card_opacity": (0, 100)}


def resolve_style(overrides):
    """Merge user settings over the defaults and clamp numbers to sane ranges."""
    style = dict(DEFAULT_STYLE)
    for key, value in (overrides or {}).items():
        if key not in style:
            continue
        if key in _LIMITS:
            lo, hi = _LIMITS[key]
            value = max(lo, min(hi, int(float(value))))
        elif isinstance(style[key], bool):
            value = bool(value)
        elif key.endswith("color"):
            value = str(value) if _is_hex(str(value)) else style[key]
        style[key] = value
    return style


def _is_hex(value):
    return len(value) == 7 and value[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in value[1:])


def _rgba(hex_color, alpha=255):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5)) + (alpha,)


def _wrap(text, font, max_width):
    """Wrap on real pixel widths rather than character counts."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and font.getlength(trial) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [""]


def render_card(text, style, video_width, path, bold=None):
    """Draw one card as a transparent PNG, sized to fit its text."""
    size = style["font_size"]
    use_bold = style["bold"] if bold is None else bold
    font = ImageFont.truetype(str(FONTS / ("Roboto-Bold.ttf" if use_bold else "Roboto-Medium.ttf")), size)

    pad = round(size * 0.7) if style["card"] else round(size * 0.2)
    max_width = round(video_width * style["width"] / 100)
    lines = _wrap(text, font, max_width - 2 * pad)
    line_h = round(size * 1.28)
    stroke = max(2, size // 14) if style["outline"] else 0

    text_w = max(font.getlength(line) for line in lines) + 2 * stroke
    width = min(max_width, round(text_w) + 2 * pad)
    height = line_h * len(lines) + 2 * pad

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if style["card"]:
        alpha = round(255 * style["card_opacity"] / 100)
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=round(size * 0.45),
                               fill=_rgba(style["card_color"], alpha))
    for i, line in enumerate(lines):
        draw.text((width / 2, pad + line_h * i + line_h / 2), line, font=font, anchor="mm",
                  fill=_rgba(style["text_color"]), stroke_width=stroke,
                  stroke_fill=_rgba(style["outline_color"]))
    img.save(path)
