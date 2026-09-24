"""Parser and validator for the shiplabel plain-text format.

A label is a block of "Key: value" lines. From and To addresses span
multiple lines, with continuation lines marked by leading whitespace:

    Carrier: UPS
    Tracking: 1Z999AA10123456784
    Service: Ground
    From: Jane Doe
      123 Main St
      Springfield, IL 62704
    To: John Smith
      456 Oak Ave Apt 3B
      Portland, OR 97201
    Weight: 2.5 kg

Multiple labels can be batched in one file, separated by a blank line.
"""

import re
from dataclasses import dataclass
from typing import Tuple


class LabelError(ValueError):
    """Raised when label text is malformed or fails validation."""


@dataclass(frozen=True)
class Address:
    name: str
    street_lines: Tuple[str, ...]
    city: str
    region: str
    postal_code: str
    country: str = "US"


@dataclass(frozen=True)
class Label:
    carrier: str
    tracking: str
    service: str
    sender: Address
    recipient: Address
    weight_value: float
    weight_unit: str


REQUIRED_FIELDS = ("carrier", "tracking", "service", "from", "to", "weight")
MULTILINE_FIELDS = frozenset({"from", "to"})
ALLOWED_SERVICES = frozenset({"GROUND", "EXPRESS", "OVERNIGHT", "2DAY", "PRIORITY", "FIRST"})

# Overnight/express are next-flight-out services carriers run with a driver
# and a scan at a street address - none of the big three will guarantee a
# PO box delivery on those tiers, so catch it at parse time instead of
# letting the label print clean and bounce at the depot.
NO_PO_BOX_SERVICES = frozenset({"OVERNIGHT", "EXPRESS"})
PO_BOX_RE = re.compile(r"^(?:p\.?\s*o\.?\s*box|post\s+office\s+box)\b", re.IGNORECASE)

# Real-world carriers use different tracking number shapes. These are close
# enough to the public formats to catch typos without pulling in a full
# carrier-specific validation library.
CARRIER_PATTERNS = {
    "UPS": re.compile(r"^1Z[0-9A-Z]{16}$"),
    "FEDEX": re.compile(r"^\d{12}$|^\d{15}$"),
    "USPS": re.compile(r"^\d{20,22}$"),
}

FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s?(.*)$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
CITY_LINE_RE = re.compile(r"^(?P<city>.+),\s*(?P<region>\S+)\s+(?P<postal>\S+)$")
WEIGHT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(kg|lb|g|oz)$", re.IGNORECASE)


def parse_labels(text: str):
    """Split a batch of labels on blank lines and parse each one."""
    blocks = re.split(r"\n\s*\n", text.strip())
    return [parse_label(block) for block in blocks if block.strip()]


def parse_label(text: str) -> Label:
    if not text.strip():
        raise LabelError("empty label")

    fields = _parse_fields(text)
    missing = [name for name in REQUIRED_FIELDS if name not in fields]
    if missing:
        raise LabelError(f"missing required field(s): {', '.join(missing)}")

    carrier = fields["carrier"][0].strip().upper()
    tracking = fields["tracking"][0].strip().upper().replace(" ", "")
    _validate_tracking(carrier, tracking)

    service = _validate_service(fields["service"][0])
    sender = _parse_address("from", fields["from"])
    recipient = _parse_address("to", fields["to"])
    _validate_po_box_restriction(service, recipient)
    weight_value, weight_unit = _parse_weight(fields["weight"][0])

    return Label(
        carrier=carrier,
        tracking=tracking,
        service=service,
        sender=sender,
        recipient=recipient,
        weight_value=weight_value,
        weight_unit=weight_unit,
    )


def _parse_fields(text: str):
    fields = {}
    current_key = None
    for raw_line in text.splitlines():
        if raw_line.strip() == "":
            continue

        if raw_line[0] in " \t":
            if current_key is None:
                raise LabelError(f"continuation line before any field: {raw_line!r}")
            if current_key not in MULTILINE_FIELDS:
                raise LabelError(f"field {current_key!r} does not accept multiple lines")
            fields[current_key].append(raw_line.strip())
            continue

        match = FIELD_RE.match(raw_line)
        if not match:
            raise LabelError(f"malformed line: {raw_line!r}")

        key = match.group(1).lower()
        if key not in REQUIRED_FIELDS:
            raise LabelError(f"unknown field: {match.group(1)!r}")
        if key in fields:
            raise LabelError(f"duplicate field: {key!r}")

        fields[key] = [match.group(2).strip()]
        current_key = key

    return fields


def _parse_address(role: str, lines):
    if len(lines) < 2:
        raise LabelError(f"{role} address needs at least a name and a city line")

    country = "US"
    if COUNTRY_RE.fullmatch(lines[-1]):
        country = lines[-1]
        lines = lines[:-1]

    if len(lines) < 3:
        raise LabelError(f"{role} address needs a name, a street line, and a city line")

    name = lines[0]
    street_lines = lines[1:-1]
    city_line = lines[-1]

    if not name:
        raise LabelError(f"{role} address name is empty")

    match = CITY_LINE_RE.match(city_line)
    if not match:
        raise LabelError(f"{role} address city line is malformed: {city_line!r}")

    city = match.group("city").strip()
    region = match.group("region")
    postal = match.group("postal")
    _validate_postal(role, country, postal)

    return Address(
        name=name,
        street_lines=tuple(street_lines),
        city=city,
        region=region,
        postal_code=postal,
        country=country,
    )


def _validate_postal(role: str, country: str, postal: str) -> None:
    if country == "US":
        if not re.fullmatch(r"\d{5}(-\d{4})?", postal):
            raise LabelError(f"{role} address has an invalid US ZIP code: {postal!r}")
    elif country == "CA":
        if not re.fullmatch(r"[A-Za-z]\d[A-Za-z]\d[A-Za-z]\d", postal):
            raise LabelError(f"{role} address has an invalid CA postal code: {postal!r}")
    elif not postal:
        raise LabelError(f"{role} address is missing a postal code")


def _validate_tracking(carrier: str, tracking: str) -> None:
    pattern = CARRIER_PATTERNS.get(carrier)
    if pattern is None:
        raise LabelError(f"unknown carrier: {carrier!r}")
    if not pattern.match(tracking):
        raise LabelError(f"{carrier} tracking number is malformed: {tracking!r}")
    if carrier == "USPS" and not _usps_checksum_valid(tracking):
        raise LabelError(f"USPS tracking number fails checksum: {tracking!r}")


def _usps_checksum_valid(tracking: str) -> bool:
    """Mod-10 check digit with alternating 3/1 weights, applied right to left."""
    digits = [int(c) for c in tracking]
    check_digit = digits[-1]
    body = digits[:-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - (total % 10)) % 10 == check_digit


def _validate_po_box_restriction(service: str, recipient: Address) -> None:
    if service not in NO_PO_BOX_SERVICES:
        return
    for line in recipient.street_lines:
        if PO_BOX_RE.match(line.strip()):
            raise LabelError(
                f"{service.title()} service cannot deliver to a PO box: {line!r}"
            )


def _validate_service(raw: str) -> str:
    service = raw.strip().upper()
    if service not in ALLOWED_SERVICES:
        raise LabelError(f"unknown service level: {raw!r}")
    return service


def _parse_weight(raw: str):
    match = WEIGHT_RE.match(raw.strip())
    if not match:
        raise LabelError(f"malformed weight: {raw!r}")
    value = float(match.group(1))
    if value <= 0:
        raise LabelError(f"weight must be positive: {raw!r}")
    return value, match.group(2).lower()
