import csv
import os
from pathlib import Path
import tempfile
import unittest

from mt2_core import (
    ABILITY_DESCRIPTION_MAX_BYTES,
    ABILITY_NAME_MAX_BYTES,
    ANIMATIONS,
    CAST_TIMES,
    CHARACTER_DESCRIPTION_MAX_BYTES,
    CHARACTER_NAME_MAX_BYTES,
    CHARACTER_TAGLINE_MAX_BYTES,
    COOLDOWNS,
    ELEMENTS,
    MT2Error,
    build_card_from_csv,
    build_card_from_document,
    extract_document,
    export_card_csv,
    export_template_csv,
    read_card,
    read_document_csv,
    validate_card,
    validate_document,
    write_document_csv,
)


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = os.environ.get("MT2_TEST_CARD")

    def require_card(self):
        if not self.card:
            self.skipTest("Set MT2_TEST_CARD to a known-good exported PNG")

    def test_confirmed_text_limits_accept_exact_maximums(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "limits.csv"
            export_template_csv(csv_path)
            document = read_document_csv(csv_path)
            document.character.update({
                "character_name": "s" * CHARACTER_NAME_MAX_BYTES,
                "character_tagline": "s" * CHARACTER_TAGLINE_MAX_BYTES,
                "character_description": "A sacred warrior who combines armour, healing, protective blessings, and radiant judgment. Paladins can lead a party as a tank or support while remaining exceptionally dependable during solo adventure",
            })
            document.skills[0]["name"] = "s" * ABILITY_NAME_MAX_BYTES
            document.skills[0]["description"] = "s" * ABILITY_DESCRIPTION_MAX_BYTES
            self.assertEqual(len(document.character["character_description"].encode("utf-8")), CHARACTER_DESCRIPTION_MAX_BYTES)
            validate_document(document)

    def test_confirmed_text_limits_reject_one_extra_byte(self):
        character_cases = (
            ("character_name", CHARACTER_NAME_MAX_BYTES),
            ("character_tagline", CHARACTER_TAGLINE_MAX_BYTES),
            ("character_description", CHARACTER_DESCRIPTION_MAX_BYTES),
        )
        for field, maximum in character_cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                csv_path = Path(directory) / "limits.csv"
                export_template_csv(csv_path)
                document = read_document_csv(csv_path)
                document.character[field] = "s" * (maximum + 1)
                with self.assertRaisesRegex(MT2Error, rf"maximum is {maximum}"):
                    validate_document(document)
        skill_cases = (("name", ABILITY_NAME_MAX_BYTES), ("description", ABILITY_DESCRIPTION_MAX_BYTES))
        for field, maximum in skill_cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                csv_path = Path(directory) / "limits.csv"
                export_template_csv(csv_path)
                document = read_document_csv(csv_path)
                document.skills[0][field] = "s" * (maximum + 1)
                with self.assertRaisesRegex(MT2Error, rf"maximum is {maximum}"):
                    validate_document(document)

    def test_card_csv_round_trip_preserves_record(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "skills.csv"
            png_path = Path(directory) / "roundtrip.png"
            export_card_csv(self.card, csv_path)
            build_card_from_csv(self.card, csv_path, png_path)
            self.assertEqual(read_card(self.card).record, read_card(png_path).record)
            self.assertTrue(validate_card(png_path)["header_matches_payload"])

    def test_changed_record_updates_length_header(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "skills.csv"
            png_path = Path(directory) / "changed.png"
            export_card_csv(self.card, csv_path)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            skill = next(row for row in rows if row["record_type"] == "SKILL")
            skill["description"] = "A deliberately longer description used to change compressed payload length."
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            result = build_card_from_csv(self.card, csv_path, png_path)
            self.assertEqual(result["compressed_bytes"], result["declared_bytes"])
            self.assertTrue(validate_card(png_path)["header_matches_payload"])

    def test_conflicting_effect_pair_is_rejected(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "skills.csv"
            png_path = Path(directory) / "bad.png"
            export_template_csv(csv_path)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            skill = next(row for row in rows if row["record_type"] == "SKILL")
            skill["effect_2_type"] = "Heal"
            skill["effect_2_value"] = "1"
            skill["effect_2_duration"] = "0"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(MT2Error):
                build_card_from_csv(self.card, csv_path, png_path)

    def test_character_fields_round_trip_and_change(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            png_path = Path(directory) / "changed_character.png"
            document = extract_document(self.card)
            document.character.update({
                "character_name": "Priest Test",
                "character_tagline": "Light answers the faithful.",
                "character_description": "A dedicated healer who protects allies and punishes the undead.",
                "health": "30", "mana": "40", "rage": "5", "speed": "6",
            })
            build_card_from_document(self.card, document, png_path)
            changed = extract_document(png_path)
            self.assertEqual(changed.character, document.character)
            self.assertTrue(validate_card(png_path)["header_matches_payload"])

    def test_schema_v2_has_schema_character_and_twelve_skills(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "class.csv"
            write_document_csv(csv_path, extract_document(self.card))
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["record_type"] for row in rows[:2]], ["SCHEMA", "CHARACTER"])
            self.assertIn("character_tagline", rows[0])
            self.assertIn("character_description", rows[0])
            self.assertEqual(sum(row["record_type"] == "REFERENCE" for row in rows), 3)
            self.assertEqual(sum(row["record_type"] == "SKILL" for row in rows), 12)
            self.assertEqual(read_document_csv(csv_path).character["character_name"], "Mage")

    def test_effect_reference_rows_cover_every_dropdown_effect(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "class.csv"
            export_template_csv(csv_path)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            references = [row for row in rows if row["record_type"] == "REFERENCE"]
            names = {
                row[f"effect_{index}_type"]
                for row in references
                for index in range(1, 9)
                if row[f"effect_{index}_type"]
            }
            from mt2_core import EFFECT_TO_INTERNAL
            self.assertEqual(names, set(EFFECT_TO_INTERNAL))

    def test_confirmed_animation_and_element_enums_are_complete(self):
        self.assertTrue({"attackdouble", "attackspin", "attackheadbutt"}.issubset(ANIMATIONS))
        self.assertTrue({"Water", "Dark"}.issubset(ELEMENTS))

    def test_confirmed_cast_and_cooldown_presets(self):
        self.assertEqual(CAST_TIMES, (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0))
        self.assertEqual(COOLDOWNS, (1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 30.0, 60.0))

    def test_unconfirmed_cast_time_is_rejected(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bad_time.csv"
            png_path = Path(directory) / "bad_time.png"
            export_template_csv(csv_path)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            next(row for row in rows if row["record_type"] == "SKILL")["cast_time"] = "0.25"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(MT2Error):
                build_card_from_csv(self.card, csv_path, png_path)

    def test_immediate_effect_with_duration_is_rejected(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bad_duration.csv"
            png_path = Path(directory) / "bad_duration.png"
            export_template_csv(csv_path)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            next(row for row in rows if row["record_type"] == "SKILL")["effect_1_duration"] = "3"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(MT2Error):
                build_card_from_csv(self.card, csv_path, png_path)

    def test_extra_csv_column_reports_a_friendly_error(self):
        self.require_card()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "extra_column.csv"
            export_template_csv(csv_path)
            lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
            lines[-1] += ","
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
            with self.assertRaisesRegex(MT2Error, "extra column"):
                read_document_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
