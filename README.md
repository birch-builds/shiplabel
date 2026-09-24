# shiplabel

A small parser and pretty printer for a plain-text shipping label format.

I keep ending up with shipping label data in ad-hoc text files (dropped
from a spreadsheet export, pasted from an email, typed by hand when
setting up a return) and wanted one place that would tell me the data
is actually usable before it gets handed to whatever prints the label:
right ZIP shape for the country, a tracking number that matches the
carrier's format, a weight with a unit attached. This is that.

It is not a client for any carrier's API. It only understands the text
format described below, validates it, and can print a normalized
version back out.

## The format

A label is a block of `Key: value` lines. `From` and `To` addresses
span multiple lines - continuation lines are marked by leading
whitespace and belong to the field above them:

```
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
```

The last line of an address is either `City, Region Postal` or a
two-letter country code, in which case the line above it is the
`City, Region Postal` line. Country defaults to `US` when omitted.

Multiple labels can go in one file, separated by a blank line.

## What gets checked

- All six fields are present: `Carrier`, `Tracking`, `Service`, `From`,
  `To`, `Weight`.
- `Carrier` is one of `UPS`, `FEDEX`, `USPS`, and `Tracking` matches
  that carrier's number format. USPS tracking numbers also get their
  check digit verified.
- `Service` is a known service level (`Ground`, `Express`, `Overnight`,
  `2Day`, `Priority`, `First`).
- `Overnight` and `Express` shipments can't go to a PO box in the `To`
  address (matched against `PO Box`, `P.O. Box`, and `Post Office Box`,
  case-insensitive, on any street line).
- Each address has a name, at least one street line, and a city line
  that parses into city / region / postal code.
- The postal code matches the shape expected for the address's country
  (US ZIP or ZIP+4, Canadian postal code; anything else just has to be
  non-empty).
- `Weight` is a positive number with a unit (`kg`, `lb`, `g`, `oz`).

Anything that fails raises `shiplabel.LabelError` with a message
naming the field and what was wrong with it.

## Usage

```python
from shiplabel import parse_label, format_label, format_summary

text = """\
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
"""

label = parse_label(text)
print(label.recipient.city, label.recipient.region)   # Portland OR
print(format_summary(label))
# UPS 1Z999AA10123456784 GROUND 2.5kg -> Portland, OR

print(format_label(label))
# CARRIER:  UPS
# TRACKING: 1Z999AA10123456784
# SERVICE:  GROUND
# ...
```

`parse_labels(text)` splits a batch of labels on blank lines and
returns a list.

## Running the tests

The test suite is table-driven: `tests/test_labels.py` has one list of
valid cases and one list of invalid cases (with the error message each
one should produce), run through `unittest`'s `subTest`. No test
runner is bundled - anything that can run `unittest` works:

```
python -m unittest discover -s tests
```

## Status

Early. No dependencies, standard library only. See the issues / commit
history for what's next.
