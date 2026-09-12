import unittest

from shiplabel import LabelError, format_label, format_summary, parse_label, parse_labels

VALID_UPS_TRACKING = "1Z999AA10123456784"
VALID_FEDEX_12 = "123456789012"
VALID_FEDEX_15 = "123456789012345"
VALID_USPS_TRACKING = "12345678901234567890"  # checksum: see parser._usps_checksum_valid
INVALID_USPS_CHECKSUM = "12345678901234567895"

BASE_FROM = ["From: Jane Doe", "  123 Main St", "  Springfield, IL 62704"]
BASE_TO = ["To: John Smith", "  456 Oak Ave Apt 3B", "  Portland, OR 97201"]


def make_label(carrier=None, tracking=None, service=None, from_lines=None, to_lines=None, weight=None):
    lines = [
        f"Carrier: {carrier if carrier is not None else 'UPS'}",
        f"Tracking: {tracking if tracking is not None else VALID_UPS_TRACKING}",
        f"Service: {service if service is not None else 'Ground'}",
    ]
    lines.extend(BASE_FROM if from_lines is None else from_lines)
    lines.extend(BASE_TO if to_lines is None else to_lines)
    lines.append(f"Weight: {weight if weight is not None else '2.5 kg'}")
    return "\n".join(lines)


class ValidLabelTests(unittest.TestCase):
    """Table-driven cases that must parse and validate cleanly."""

    def test_valid_cases(self):
        cases = [
            ("plain ups label", make_label(), {
                "carrier": "UPS", "tracking": VALID_UPS_TRACKING, "service": "GROUND",
            }),
            ("lowercase carrier and service are normalized", make_label(carrier="ups", service="ground"), {
                "carrier": "UPS", "service": "GROUND",
            }),
            ("fedex 12-digit tracking", make_label(carrier="fedex", tracking=VALID_FEDEX_12, service="express"), {
                "carrier": "FEDEX", "tracking": VALID_FEDEX_12,
            }),
            ("fedex 15-digit tracking", make_label(carrier="fedex", tracking=VALID_FEDEX_15, service="express"), {
                "carrier": "FEDEX", "tracking": VALID_FEDEX_15,
            }),
            ("usps tracking with valid checksum", make_label(carrier="usps", tracking=VALID_USPS_TRACKING, service="priority"), {
                "carrier": "USPS", "tracking": VALID_USPS_TRACKING,
            }),
            ("zip+4 postal code", make_label(from_lines=["From: Jane Doe", "  123 Main St", "  Springfield, IL 62704-1234"]), {
                "sender_postal": "62704-1234",
            }),
            ("address with explicit country line", make_label(from_lines=["From: Jane Doe", "  123 Main St", "  Springfield, IL 62704", "  US"]), {
                "sender_country": "US",
            }),
            ("canadian postal code", make_label(to_lines=["To: John Smith", "  1 Rue Principale", "  Montreal, QC H2X1Y6", "  CA"]), {
                "recipient_country": "CA", "recipient_postal": "H2X1Y6",
            }),
            ("multi-line street address", make_label(from_lines=["From: Jane Doe", "  Suite 400", "  123 Main St", "  Springfield, IL 62704"]), {
                "sender_street_count": 2,
            }),
            ("integer weight prints without decimal", make_label(weight="3 kg"), {
                "weight_value": 3.0, "weight_unit": "kg",
            }),
            ("fractional weight in pounds", make_label(weight="0.5 lb"), {
                "weight_value": 0.5, "weight_unit": "lb",
            }),
        ]

        for name, text, expected in cases:
            with self.subTest(name=name):
                label = parse_label(text)
                if "carrier" in expected:
                    self.assertEqual(label.carrier, expected["carrier"])
                if "tracking" in expected:
                    self.assertEqual(label.tracking, expected["tracking"])
                if "service" in expected:
                    self.assertEqual(label.service, expected["service"])
                if "sender_postal" in expected:
                    self.assertEqual(label.sender.postal_code, expected["sender_postal"])
                if "sender_country" in expected:
                    self.assertEqual(label.sender.country, expected["sender_country"])
                if "recipient_country" in expected:
                    self.assertEqual(label.recipient.country, expected["recipient_country"])
                if "recipient_postal" in expected:
                    self.assertEqual(label.recipient.postal_code, expected["recipient_postal"])
                if "sender_street_count" in expected:
                    self.assertEqual(len(label.sender.street_lines), expected["sender_street_count"])
                if "weight_value" in expected:
                    self.assertEqual(label.weight_value, expected["weight_value"])
                if "weight_unit" in expected:
                    self.assertEqual(label.weight_unit, expected["weight_unit"])


class InvalidLabelTests(unittest.TestCase):
    """Table-driven cases that must be rejected, with a reason to check."""

    def test_invalid_cases(self):
        cases = [
            ("empty text", "", "empty label"),
            ("missing service field", "\n".join([
                "Carrier: UPS", f"Tracking: {VALID_UPS_TRACKING}",
                *BASE_FROM, *BASE_TO, "Weight: 2.5 kg",
            ]), "missing required field"),
            ("unknown field name", make_label() + "\nRefer: xyz", "unknown field"),
            ("duplicate field", make_label() + "\nCarrier: FEDEX", "duplicate field"),
            ("continuation on a single-line field", "Weight: 2.5 kg\n  extra", "does not accept multiple lines"),
            ("unknown carrier", make_label(carrier="DHL"), "unknown carrier"),
            ("unknown service level", make_label(service="Teleport"), "unknown service level"),
            ("ups tracking too short", make_label(tracking="1Z12345"), "malformed"),
            ("usps tracking wrong checksum", make_label(carrier="usps", tracking=INVALID_USPS_CHECKSUM, service="priority"), "checksum"),
            ("weight with no unit", make_label(weight="2.5"), "malformed weight"),
            ("zero weight", make_label(weight="0 kg"), "must be positive"),
            ("negative weight", make_label(weight="-1 kg"), "malformed weight"),
            ("invalid us zip", make_label(to_lines=["To: John Smith", "  1 Main St", "  Portland, OR ABCDE"]), "invalid US ZIP"),
            ("address missing street line", make_label(from_lines=["From: Jane Doe", "  Springfield, IL 62704"]), "needs a name, a street line"),
            ("address with empty name", make_label(from_lines=["From: ", "  123 Main St", "  Springfield, IL 62704"]), "name is empty"),
            ("malformed city line", make_label(from_lines=["From: Jane Doe", "  123 Main St", "  Springfield IL"]), "malformed"),
        ]

        for name, text, expected_message in cases:
            with self.subTest(name=name):
                with self.assertRaises(LabelError) as ctx:
                    parse_label(text)
                self.assertIn(expected_message, str(ctx.exception))


class BatchParsingTests(unittest.TestCase):
    def test_two_labels_separated_by_blank_line(self):
        text = make_label() + "\n\n" + make_label(carrier="fedex", tracking=VALID_FEDEX_12, service="express")
        labels = parse_labels(text)
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0].carrier, "UPS")
        self.assertEqual(labels[1].carrier, "FEDEX")

    def test_trailing_blank_lines_are_tolerated(self):
        labels = parse_labels(make_label() + "\n\n\n")
        self.assertEqual(len(labels), 1)


class PrinterTests(unittest.TestCase):
    def test_format_label_is_stable_across_input_spacing(self):
        loose = "Carrier:  UPS\nTracking: " + VALID_UPS_TRACKING + "\nService: ground\n"
        loose += "\n".join(BASE_FROM) + "\n" + "\n".join(BASE_TO) + "\nWeight: 2.5 kg"
        label = parse_label(loose)
        printed = format_label(label)
        self.assertIn("CARRIER:  UPS", printed)
        self.assertIn("SERVICE:  GROUND", printed)
        self.assertIn("Springfield, IL 62704", printed)

    def test_format_summary_contains_destination(self):
        label = parse_label(make_label())
        summary = format_summary(label)
        self.assertIn("Portland, OR", summary)
        self.assertIn(VALID_UPS_TRACKING, summary)


if __name__ == "__main__":
    unittest.main()
