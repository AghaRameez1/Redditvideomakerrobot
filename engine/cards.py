"""Text cards: one transparent PNG per sentence, or full-frame word-by-word captions."""
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
    "captions": "cards",    # "cards": one card per sentence. "words": a few words at a time, spoken word highlighted
    "highlight_color": "#ffe14d",
    "words_at_once": 3,     # words shown together in "words" mode, 1-5
}

_LIMITS = {"blur": (0, 40), "dim": (0, 80), "position": (5, 95), "width": (40, 96),
           "font_size": (28, 140), "card_opacity": (0, 100), "words_at_once": (1, 5)}
_CHOICES = {"captions": ("cards", "words")}


def resolve_style(overrides):
    """Merge user settings over the defaults and clamp numbers to sane ranges."""
    style = dict(DEFAULT_STYLE)
    for key, value in (overrides or {}).items():
        if key not in style:
            continue
        if key in _LIMITS:
            lo, hi = _LIMITS[key]
            try:
                value = max(lo, min(hi, int(float(value))))
            except (TypeError, ValueError):
                value = style[key]
        elif key in _CHOICES:
            value = value if value in _CHOICES[key] else style[key]
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


def render_watermark(text, path, size=30):
    """A small semi-transparent label, e.g. "Made with Script Studio", for free-plan videos."""
    font = ImageFont.truetype(str(FONTS / "Roboto-Medium.ttf"), size)
    pad_x, pad_y = round(size * 0.6), round(size * 0.35)
    width, height = round(font.getlength(text)) + 2 * pad_x, round(size * 1.2) + 2 * pad_y
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=height // 2, fill=(0, 0, 0, 140))
    draw.text((width / 2, height / 2), text, font=font, anchor="mm", fill=(255, 255, 255, 230))
    img.save(path)


def _word_font(style):
    return ImageFont.truetype(str(FONTS / ("Roboto-Bold.ttf" if style["bold"] else "Roboto-Medium.ttf")),
                              style["font_size"])


def render_word_frame(words, highlight, style, size, path):
    """One full-frame transparent PNG showing `words`, with words[highlight] in the highlight colour.

    Drawn at full video size, so all frames line up and can be played as one caption track.
    """
    width, height = size
    font = _word_font(style)
    font_size = style["font_size"]
    stroke = max(2, font_size // 14) if style["outline"] or not style["card"] else 0
    space = font.getlength(" ")
    max_w = width * style["width"] / 100 - (2 * font_size * 0.5 if style["card"] else 0)

    lines, line = [], []  # wrap word by word, keeping each word's index
    for i, word in enumerate(words):
        trial = line + [(i, word)]
        if line and sum(font.getlength(w) for _, w in trial) + space * (len(trial) - 1) > max_w:
            lines.append(line)
            line = [(i, word)]
        else:
            line = trial
    lines.append(line)

    line_h = round(font_size * 1.28)
    block_h = line_h * len(lines)
    centre_y = height * style["position"] / 100
    top = max(0, min(height - block_h, centre_y - block_h / 2))
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    line_widths = [sum(font.getlength(w) for _, w in ln) + space * (len(ln) - 1) for ln in lines]
    if style["card"]:
        pad = round(font_size * 0.5)
        box_w = max(line_widths) + 2 * pad
        alpha = round(255 * style["card_opacity"] / 100)
        draw.rounded_rectangle([(width - box_w) / 2, top - pad, (width + box_w) / 2, top + block_h + pad],
                               radius=round(font_size * 0.45), fill=_rgba(style["card_color"], alpha))
    for row, (ln, line_w) in enumerate(zip(lines, line_widths)):
        x = (width - line_w) / 2
        y = top + row * line_h + line_h / 2
        for i, word in ln:
            colour = style["highlight_color"] if i == highlight else style["text_color"]
            draw.text((x, y), word, font=font, anchor="lm", fill=_rgba(colour), stroke_width=stroke,
                      stroke_fill=_rgba(style["outline_color"]))
            x += font.getlength(word) + space
    img.save(path, optimize=False, compress_level=1)
