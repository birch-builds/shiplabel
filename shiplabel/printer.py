"""Pretty printer for parsed labels.

This does not try to reproduce the exact text a Label was parsed from -
it normalizes casing and spacing so the same Label always prints the
same way, regardless of how the source text was formatted.
"""

from .parser import Address, Label


def format_address(address: Address) -> str:
    lines = [
        address.name,
        *address.street_lines,
        f"{address.city}, {address.region} {address.postal_code}",
        address.country,
    ]
    return "\n".join("  " + line for line in lines)


def format_label(label: Label) -> str:
    parts = [
        f"CARRIER:  {label.carrier}",
        f"TRACKING: {label.tracking}",
        f"SERVICE:  {label.service}",
        "",
        "FROM",
        format_address(label.sender),
        "",
        "TO",
        format_address(label.recipient),
        "",
        f"WEIGHT:   {_format_weight(label.weight_value)} {label.weight_unit}",
    ]
    return "\n".join(parts)


def format_summary(label: Label) -> str:
    weight = f"{_format_weight(label.weight_value)}{label.weight_unit}"
    destination = f"{label.recipient.city}, {label.recipient.region}"
    return f"{label.carrier} {label.tracking} {label.service} {weight} -> {destination}"


def _format_weight(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"
