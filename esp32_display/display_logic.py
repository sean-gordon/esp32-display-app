"""The three-character rendering contract shared with the ESP32 firmware."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

GLYPHS = {
    "0":0x3F,"1":0x06,"2":0x5B,"3":0x4F,"4":0x66,
    "5":0x6D,"6":0x7D,"7":0x07,"8":0x7F,"9":0x6F,
    "A":0x77,"B":0x7C,"C":0x39,"D":0x5E,"E":0x79,"F":0x71,
    "G":0x7D,"H":0x76,"I":0x06,"J":0x1E,"L":0x38,"N":0x54,
    "O":0x3F,"P":0x73,"R":0x50,"S":0x6D,"T":0x78,"U":0x3E,"Y":0x6E,
    "-":0x40,"_":0x08," ":0,
}
GLYPHS.update({c.lower():v for c,v in list(GLYPHS.items()) if c.isalpha()})
GLYPHS.update({"c":0x58,"o":0x5C})


def validate_value(value):
    if not isinstance(value, str):
        raise ValueError("Enter text containing at most three characters.")
    if len(value) > 3:
        raise ValueError("The display supports at most three characters; values are never truncated.")
    if any(c not in GLYPHS for c in value):
        raise ValueError("Use digits, spaces, - or _, or letters A B C D E F G H I J L N O P R S T U Y. No decimal point is wired.")
    return value


def source_value(state, format_mode):
    if not isinstance(state, str) or state.lower() in {"unknown", "unavailable", "none"}:
        return "Err", "Source is unavailable."
    if format_mode == "integer":
        try:
            n = Decimal(state)
            if not n.is_finite() or n > 1000 or n < -100:
                return "Err", "Value is outside the display range (-99 to 999)."
            value = str(n.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if value == "-0": value = "0"
        except (InvalidOperation, ValueError):
            return "Err", "Source is not a finite number."
    else:
        value = state
    try:
        return validate_value(value), ""
    except ValueError as exc:
        return "Err", str(exc)


def render_masks(value):
    validate_value(value)
    return [GLYPHS[c] for c in value.rjust(3)]
