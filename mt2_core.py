from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

from PIL import Image


SKILL_COUNT = 12
SCHEMA_VERSION = "2"
UNLOCK_LEVELS = [1, 1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
MAX_EFFECTS = 8
BLANK_SENTINEL = "<blank>"
CHARACTER_NAME_MAX_BYTES = 20
CHARACTER_TAGLINE_MAX_BYTES = 80
CHARACTER_DESCRIPTION_MAX_BYTES = 200
ABILITY_NAME_MAX_BYTES = 20
ABILITY_DESCRIPTION_MAX_BYTES = 200

BASE_COLUMNS = [
    "slot", "unlock_level", "name", "definition", "activation_type",
    "cast_time", "cooldown", "range_type", "target_area", "element",
    "path", "animation", "use_weapon_animation", "health_cost", "mana_cost",
    "rage_cost", "description",
]
EFFECT_COLUMNS = [
    column
    for index in range(1, MAX_EFFECTS + 1)
    for column in (f"effect_{index}_type", f"effect_{index}_value", f"effect_{index}_duration")
]
META_COLUMNS = [
    "record_type", "schema_version", "character_name", "character_tagline",
    "character_description", "health", "mana", "rage", "speed",
]
CSV_COLUMNS = META_COLUMNS + BASE_COLUMNS + EFFECT_COLUMNS
LEGACY_CSV_COLUMNS = BASE_COLUMNS + EFFECT_COLUMNS

DEFINITIONS = {"Attack", "Heal", "Buff", "Debuff", ""}
ACTIVATION_TYPES = {"Instant"}
CAST_TIMES = (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0)
COOLDOWNS = (1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 30.0, 60.0)
ELEMENTS = {"Physical", "Light", "Dark", "Fire", "Ice", "Water", "Electric", "Earth"}
PATHS = {"Arc", "Straight", "Missile", "Skybeam"}
ANIMATIONS = {
    "attack", "attackdouble", "attackheavy", "attackspin", "attackheadbutt",
    "cast", "castcharge", "castswish", "castforce",
}
RANGE_VALUES = {"Self": 0.0, "Melee": 5.0, "Missile": 20.0}
AREA_VALUES = {"Single": 0.0, "Small Area": 5.0, "Large Area": 15.0}


class MT2Error(Exception):
    pass


@dataclass
class CardData:
    image: Image.Image
    positions: list[tuple[int, int]]
    header: bytearray
    compressed: bytes
    record: bytes
    declared_length: int


@dataclass
class ClassDocument:
    character: dict[str, str]
    skills: list[dict[str, str]]


def _validate_utf8_length(value: str, maximum: int, label: str) -> None:
    byte_count = len(value.encode("utf-8"))
    if byte_count > maximum:
        raise MT2Error(f"{label} is {byte_count} UTF-8 bytes; maximum is {maximum}.")


def signature(name: str) -> bytes:
    encoded = name.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(encoded)) + encoded


def _carrier_positions(image: Image.Image) -> list[tuple[int, int]]:
    return [
        (x, y)
        for y in range(image.height - 1, -1, -1)
        for x in range(image.width)
        if image.getpixel((x, y))[3] > 0
    ]


def _unpack_lsb_bytes(image: Image.Image, positions: list[tuple[int, int]]) -> bytes:
    bits: list[int] = []
    for x, y in positions:
        r, g, b, _ = image.getpixel((x, y))
        bits.extend((r & 1, g & 1, b & 1))
    return bytes(
        sum(bits[index + bit] << bit for bit in range(8))
        for index in range(0, len(bits) - 7, 8)
    )


def _embed_lsb_bytes(image: Image.Image, positions: list[tuple[int, int]], data: bytes, clear_bytes: int | None = None) -> None:
    bits = [(byte >> bit) & 1 for byte in data for bit in range(8)]
    bit_count = max(len(data), clear_bytes or 0) * 8
    if bit_count > len(positions) * 3:
        raise MT2Error("The compressed class data is too large for this PNG carrier.")
    pixels = image.load()
    for bit_index in range(bit_count):
        pixel_index, channel = divmod(bit_index, 3)
        x, y = positions[pixel_index]
        rgba = list(pixels[x, y])
        bit = bits[bit_index] if bit_index < len(bits) else 0
        rgba[channel] = (rgba[channel] & 0xFE) | bit
        pixels[x, y] = tuple(rgba)


def read_card(path: str | Path) -> CardData:
    try:
        image = Image.open(path).convert("RGBA")
    except Exception as exc:
        raise MT2Error(f"Could not open PNG: {exc}") from exc
    if image.size != (280, 500):
        raise MT2Error(f"Expected a 280x500 MT2 card, received {image.width}x{image.height}.")
    positions = _carrier_positions(image)
    if len(positions) < 100:
        raise MT2Error("PNG does not contain enough carrier pixels.")
    header = bytearray(_unpack_lsb_bytes(image, positions[:50]))
    if len(header) < 18:
        raise MT2Error("MT2 card header is incomplete.")
    if header[:4] != b"\x00\x00\x00\x2a":
        raise MT2Error("PNG does not have the expected MT2 class-card header.")
    declared_length = struct.unpack_from(">H", header, 8)[0]
    payload = _unpack_lsb_bytes(image, positions[50:])
    decoder = zlib.decompressobj()
    try:
        record = decoder.decompress(payload) + decoder.flush()
    except zlib.error as exc:
        raise MT2Error(f"Embedded payload is not valid zlib data: {exc}") from exc
    compressed_length = len(payload) - len(decoder.unused_data)
    compressed = payload[:compressed_length]
    if not record.startswith(b"\x00\x08RecordV2"):
        raise MT2Error("Embedded payload is not an MT2 RecordV2 character definition.")
    return CardData(image, positions, header, compressed, record, declared_length)


def write_card(card: CardData, record: bytes, output_path: str | Path) -> None:
    compressed = zlib.compress(record, level=6)
    if len(compressed) > 0xFFFF:
        raise MT2Error("Compressed payload exceeds the MT2 16-bit length field.")
    image = card.image.copy()
    header = bytearray(card.header)
    struct.pack_into(">H", header, 8, len(compressed))
    _embed_lsb_bytes(image, card.positions[:50], bytes(header))
    _embed_lsb_bytes(image, card.positions[50:], compressed, clear_bytes=len(card.compressed))
    image.save(output_path, format="PNG", optimize=False)

    check = read_card(output_path)
    if check.declared_length != len(compressed):
        raise MT2Error("Output verification failed: payload length header is incorrect.")
    if check.record != record:
        raise MT2Error("Output verification failed: embedded RecordV2 changed during save.")


def _scalar(name: str, tag: int, value) -> bytes:
    if tag == 2:
        encoded = str(value).encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise MT2Error(f"Text in {name} is too long.")
        primitive = b"\x02" + struct.pack(">H", len(encoded)) + encoded
    elif tag == 3:
        primitive = b"\x03" + struct.pack("<f", float(value))
    elif tag == 4:
        primitive = b"\x04" + struct.pack(">I", int(value))
    else:
        raise MT2Error(f"Unsupported scalar tag {tag}.")
    return signature(name) + struct.pack(">I", 1) + primitive + b"\x00\x00\x00\x00"


def _composite(name: str, children: list[bytes]) -> bytes:
    return signature(name) + struct.pack(">Q", len(children)) + b"".join(children)


def _scalar_span(record: bytes, name: str) -> tuple[int, int]:
    start = record.find(signature(name))
    if start < 0:
        raise MT2Error(f"Ability field {name!r} was not found.")
    cursor = start + len(signature(name))
    count = struct.unpack_from(">I", record, cursor)[0]
    if count != 1:
        raise MT2Error(f"Ability field {name!r} has unsupported value count {count}.")
    cursor += 4
    tag = record[cursor]
    cursor += 1
    if tag == 2:
        length = struct.unpack_from(">H", record, cursor)[0]
        cursor += 2 + length
    elif tag in (3, 4):
        cursor += 4
    else:
        raise MT2Error(f"Ability field {name!r} has unsupported type tag {tag}.")
    if record[cursor:cursor + 4] != b"\x00\x00\x00\x00":
        raise MT2Error(f"Ability field {name!r} has an invalid terminator.")
    return start, cursor + 4


def _replace_scalar(record: bytes, name: str, tag: int, value) -> bytes:
    start, end = _scalar_span(record, name)
    return record[:start] + _scalar(name, tag, value) + record[end:]


def _find_scalar_spans(record: bytes, name: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Return complete scalar spans in a bounded record section."""
    spans: list[tuple[int, int]] = []
    marker = signature(name)
    limit = len(record) if end is None else end
    cursor = start
    while True:
        found = record.find(marker, cursor, limit)
        if found < 0:
            return spans
        local_start, local_end = _scalar_span(record[found:limit], name)
        spans.append((found + local_start, found + local_end))
        cursor = found + len(marker)


def _read_scalar_at(record: bytes, span: tuple[int, int], name: str):
    return _read_scalar(record[span[0]:span[1]], name)


def _replace_span(record: bytes, span: tuple[int, int], name: str, tag: int, value) -> bytes:
    return record[:span[0]] + _scalar(name, tag, value) + record[span[1]:]


def _read_scalar(record: bytes, name: str):
    start = record.find(signature(name))
    if start < 0:
        raise MT2Error(f"Ability field {name!r} was not found.")
    cursor = start + len(signature(name)) + 4
    tag = record[cursor]
    cursor += 1
    if tag == 2:
        length = struct.unpack_from(">H", record, cursor)[0]
        return record[cursor + 2:cursor + 2 + length].decode("utf-8")
    if tag == 3:
        return struct.unpack_from("<f", record, cursor)[0]
    if tag == 4:
        return struct.unpack_from(">I", record, cursor)[0]
    raise MT2Error(f"Unsupported scalar type tag {tag} in {name!r}.")


def _split_abilities(record: bytes) -> tuple[int, list[bytes], int]:
    ability_start = record.find(signature("ability"))
    marker = signature("mmoAbilityPrototype")
    starts: list[int] = []
    cursor = ability_start
    while True:
        cursor = record.find(marker, cursor + 1)
        if cursor < 0:
            break
        starts.append(cursor)
    if len(starts) != SKILL_COUNT:
        raise MT2Error(f"Expected {SKILL_COUNT} ability slots, found {len(starts)}.")
    boss_start = record.find(signature("bossPhases"), starts[-1])
    if ability_start < 0 or boss_start < 0:
        raise MT2Error("Could not locate the ability container boundaries.")
    abilities = [record[start:end] for start, end in zip(starts, starts[1:] + [boss_start])]
    return ability_start, abilities, boss_start


def _effect_node(kind: str, attribute_id: int, adjustment: float, duration: float, target: str) -> bytes:
    return _composite("mmoAbilityEffect", [
        _scalar("type", 2, kind),
        _scalar("attributeId", 4, attribute_id),
        _scalar("adjustment", 3, adjustment),
        _scalar("duration", 3, duration),
        _scalar("target", 2, target),
    ])


def _parse_effect_container(ability: bytes, container_name: str) -> list[tuple[str, int, float, float, str]]:
    start = ability.find(signature(container_name))
    if start < 0:
        raise MT2Error(f"Missing {container_name} container.")
    if container_name == "cost":
        end = ability.find(signature("effect"), start + 1)
    else:
        end = ability.find(signature("displaySlot"), start)
    raw = ability[start:end]
    expected = struct.unpack_from(">Q", raw, len(signature(container_name)))[0]
    marker = signature("mmoAbilityEffect")
    starts: list[int] = []
    cursor = 0
    while True:
        cursor = raw.find(marker, cursor)
        if cursor < 0:
            break
        starts.append(cursor)
        cursor += 1
    ends = starts[1:] + [len(raw)]
    effects = [
        (
            str(_read_scalar(raw[a:b], "type")),
            int(_read_scalar(raw[a:b], "attributeId")),
            float(_read_scalar(raw[a:b], "adjustment")),
            float(_read_scalar(raw[a:b], "duration")),
            str(_read_scalar(raw[a:b], "target")),
        )
        for a, b in zip(starts, ends)
    ]
    if expected != len(effects):
        raise MT2Error(f"{container_name} effect count is inconsistent.")
    return effects


EFFECT_TO_INTERNAL = {
    "Damage": ("attribute", 0, -1),
    "Heal": ("attribute", 0, 1),
    "Damage Over Time": ("attribute_timed", 0, -1),
    "Heal Over Time": ("attribute_timed", 0, 1),
    "Drain Mana": ("attribute", 1, -1),
    "Charge Mana": ("attribute", 1, 1),
    "Drain Mana Over Time": ("attribute_timed", 1, -1),
    "Charge Mana Over Time": ("attribute_timed", 1, 1),
    "Reduce Rage": ("attribute", 2, -1),
    "Generate Rage": ("attribute", 2, 1),
    "Drain Rage Over Time": ("attribute_timed", 2, -1),
    "Generate Rage Over Time": ("attribute_timed", 2, 1),
    "Siphon Health": ("siphon", 0, -1),
    "Siphon Mana": ("siphon", 1, -1),
    "Siphon Rage": ("siphon", 2, -1),
    "Slow": ("slow", 0, 0),
    "Root In Place": ("root", 0, 0),
    "Stun": ("stun", 0, 0),
    "Protect": ("protect", 0, 1),
    "Weaken": ("protect", 0, -1),
    "Taunt": ("taunt", 0, 0),
}

EFFECT_HELP = {
    "Damage": ("health amount", "0", "Remove health from the target immediately."),
    "Heal": ("health amount", "0", "Restore health to the target immediately."),
    "Damage Over Time": ("health amount over duration", "> 0 seconds", "Damage the target over the entered duration."),
    "Heal Over Time": ("health amount over duration", "> 0 seconds", "Heal the target over the entered duration."),
    "Drain Mana": ("mana amount", "0", "Remove mana from the target immediately."),
    "Charge Mana": ("mana amount", "0", "Give mana to the target immediately."),
    "Drain Mana Over Time": ("mana amount over duration", "> 0 seconds", "Remove mana from the target over time."),
    "Charge Mana Over Time": ("mana amount over duration", "> 0 seconds", "Give mana to the target over time."),
    "Reduce Rage": ("rage amount", "0", "Remove rage from the target immediately."),
    "Generate Rage": ("rage amount", "0", "Give rage to the target immediately."),
    "Drain Rage Over Time": ("rage amount over duration", "> 0 seconds", "Remove rage from the target over time."),
    "Generate Rage Over Time": ("rage amount over duration", "> 0 seconds", "Give rage to the target over time."),
    "Siphon Health": ("health amount", "0", "Drain health from the target and return it to the user."),
    "Siphon Mana": ("mana amount", "0", "Drain mana from the target and return it to the user."),
    "Siphon Rage": ("rage amount", "0", "Drain rage from the target and return it to the user."),
    "Slow": ("0 (ignored; no percentage)", "> 0 seconds", "Slow the target for the duration; the game exposes duration only."),
    "Root In Place": ("0 (ignored)", "> 0 seconds", "Prevent the target from moving for the duration."),
    "Stun": ("0 (ignored)", "> 0 seconds", "Prevent the target from acting for the duration."),
    "Protect": ("protection percentage", "> 0 seconds", "Reduce damage received by the target for the duration."),
    "Weaken": ("weakening percentage", "> 0 seconds", "Increase damage received by the target for the duration."),
    "Taunt": ("0 (ignored)", "> 0 seconds", "Force/encourage the target to attack the user for the duration."),
}


def _normalise_choice(value: str, choices: set[str], field: str) -> str:
    lookup = {choice.casefold(): choice for choice in choices}
    key = value.strip().casefold()
    if key not in lookup:
        raise MT2Error(f"Unknown {field} {value!r}. Allowed: {', '.join(sorted(choices))}")
    return lookup[key]


def _number(value: str, field: str, default: float | None = None) -> float:
    text = value.strip()
    if not text and default is not None:
        return default
    try:
        return float(text)
    except ValueError as exc:
        raise MT2Error(f"{field} must be a number, received {value!r}.") from exc


def _boolean(value: str, field: str) -> str:
    key = value.strip().casefold()
    if key in {"true", "yes", "1"}:
        return "true"
    if key in {"false", "no", "0"}:
        return "false"
    raise MT2Error(f"{field} must be true or false.")


def _preset_number(value: str, presets: tuple[float, ...], field: str) -> float:
    number = _number(value, field)
    for preset in presets:
        if abs(number - preset) < 0.0001:
            return preset
    allowed = ", ".join(_format_number(item) for item in presets)
    raise MT2Error(f"{field} must be one of the confirmed game presets: {allowed}.")


def _effect_from_csv(effect_type: str, value: str, duration: str, row_label: str):
    canonical = _normalise_choice(effect_type, set(EFFECT_TO_INTERNAL), f"{row_label} effect type")
    kind, attribute_id, sign = EFFECT_TO_INTERNAL[canonical]
    amount = abs(_number(value, f"{row_label} {canonical} value", default=0.0))
    seconds = abs(_number(duration, f"{row_label} {canonical} duration", default=0.0))
    if kind in {"attribute_timed", "protect", "slow", "root", "stun", "taunt"} and seconds <= 0:
        raise MT2Error(f"{row_label} {canonical} requires a duration greater than zero.")
    if kind in {"attribute", "siphon"} and seconds != 0:
        raise MT2Error(f"{row_label} {canonical} is immediate and requires duration 0.")
    adjustment = 0.0 if sign == 0 else amount * sign
    return canonical, (kind, attribute_id, adjustment, seconds, "Target")


def _effect_to_csv(effect: tuple[str, int, float, float, str]) -> tuple[str, str, str]:
    kind, attribute_id, adjustment, duration, _target = effect
    if kind == "attribute":
        labels = {0: ("Damage", "Heal"), 1: ("Drain Mana", "Charge Mana"), 2: ("Reduce Rage", "Generate Rage")}
        label = labels[attribute_id][adjustment > 0]
    elif kind == "attribute_timed":
        labels = {
            0: ("Damage Over Time", "Heal Over Time"),
            1: ("Drain Mana Over Time", "Charge Mana Over Time"),
            2: ("Drain Rage Over Time", "Generate Rage Over Time"),
        }
        label = labels[attribute_id][adjustment > 0]
    elif kind == "siphon":
        label = {0: "Siphon Health", 1: "Siphon Mana", 2: "Siphon Rage"}[attribute_id]
    elif kind == "protect":
        label = "Protect" if adjustment > 0 else "Weaken"
    else:
        label = {"slow": "Slow", "root": "Root In Place", "stun": "Stun", "taunt": "Taunt"}.get(kind)
        if label is None:
            raise MT2Error(f"Unsupported effect type in card: {kind!r}.")
    return label, _format_number(abs(adjustment)), _format_number(duration)


def _format_number(value: float | int) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return format(number, ".7g")


def _range_name(target_type: str, value: float) -> str:
    if target_type == "Self":
        return "Self"
    for name, known in RANGE_VALUES.items():
        if name != "Self" and abs(value - known) < 0.0001:
            return name
    return _format_number(value)


def _area_name(value: float) -> str:
    for name, known in AREA_VALUES.items():
        if abs(value - known) < 0.0001:
            return name
    return _format_number(value)


def extract_character(record: bytes) -> dict[str, str]:
    base_start = record.find(signature("attributeParametersSet"))
    elite_start = record.find(signature("eliteAttributeParametersSet"))
    costume_start = record.find(signature("costumeName"))
    ability_start = record.find(signature("ability"))
    if not (0 <= base_start < elite_start < costume_start < ability_start):
        raise MT2Error("Could not locate the character-stat record boundaries.")
    max_spans = _find_scalar_spans(record, "max", base_start, elite_start)
    if len(max_spans) != 3:
        raise MT2Error(f"Expected three base character resources, found {len(max_spans)}.")
    name_spans = _find_scalar_spans(record, "name", elite_start, costume_start)
    speed_spans = _find_scalar_spans(record, "speed", costume_start, ability_start)
    if len(name_spans) != 1 or len(speed_spans) != 1:
        raise MT2Error("Character name or movement speed is ambiguous in this card layout.")
    quote = str(_read_scalar(record, "quote"))
    fluff = str(_read_scalar(record, "fluff"))
    return {
        "character_name": str(_read_scalar_at(record, name_spans[0], "name")),
        "character_tagline": "" if quote == "{charactercard_quote_default}" else quote,
        "character_description": "" if fluff == "{charactercard_fluff_default}" else fluff,
        "health": _format_number(_read_scalar_at(record, max_spans[0], "max")),
        "mana": _format_number(_read_scalar_at(record, max_spans[1], "max")),
        "rage": _format_number(_read_scalar_at(record, max_spans[2], "max")),
        "speed": _format_number(_read_scalar_at(record, speed_spans[0], "speed")),
    }


def _configure_character(record: bytes, character: dict[str, str]) -> bytes:
    name = character.get("character_name", "").strip()
    if not name:
        raise MT2Error("Character name cannot be empty.")
    values = {
        field: _number(character.get(field, ""), f"Character {field}")
        for field in ("health", "mana", "rage", "speed")
    }
    if values["health"] <= 0:
        raise MT2Error("Character health must be greater than zero.")
    if any(values[field] < 0 for field in ("mana", "rage", "speed")):
        raise MT2Error("Character mana, rage and speed cannot be negative.")

    # Replace from the end towards the start so earlier offsets remain valid.
    base_start = record.find(signature("attributeParametersSet"))
    elite_start = record.find(signature("eliteAttributeParametersSet"))
    costume_start = record.find(signature("costumeName"))
    ability_start = record.find(signature("ability"))
    base_spans = _find_scalar_spans(record, "max", base_start, elite_start)
    elite_spans = _find_scalar_spans(record, "max", elite_start, costume_start)
    name_spans = _find_scalar_spans(record, "name", elite_start, costume_start)
    speed_spans = _find_scalar_spans(record, "speed", costume_start, ability_start)
    if len(base_spans) != 3 or len(elite_spans) != 3 or len(name_spans) != 1 or len(speed_spans) != 1:
        raise MT2Error("This card's character-stat layout is not supported safely.")
    replacements = [
        (speed_spans[0], "speed", 3, values["speed"]),
        (name_spans[0], "name", 2, name),
        (elite_spans[2], "max", 3, values["rage"]),
        (elite_spans[1], "max", 3, values["mana"]),
        (elite_spans[0], "max", 3, values["health"] * 2.0),
        (base_spans[2], "max", 3, values["rage"]),
        (base_spans[1], "max", 3, values["mana"]),
        (base_spans[0], "max", 3, values["health"]),
    ]
    for span, field, tag, value in sorted(replacements, reverse=True):
        record = _replace_span(record, span, field, tag, value)
    for csv_field, record_field in (("character_tagline", "quote"), ("character_description", "fluff")):
        text = character.get(csv_field, "").strip()
        if text:
            value = "" if text.casefold() == BLANK_SENTINEL else text
            record = _replace_scalar(record, record_field, 2, value)
    return record


def _blank_skill(slot: int) -> dict[str, str]:
    row = {column: "" for column in LEGACY_CSV_COLUMNS}
    row.update({
        "slot": str(slot), "unlock_level": str(UNLOCK_LEVELS[slot - 1]),
        "name": f"Skill {slot}", "definition": "Attack", "activation_type": "Instant",
        "cast_time": "0", "cooldown": "1", "range_type": "Melee", "target_area": "Single",
        "element": "Physical", "path": "Arc", "animation": "attack", "use_weapon_animation": "true",
        "health_cost": "0", "mana_cost": "0", "rage_cost": "0", "description": "",
        "effect_1_type": "Damage", "effect_1_value": "1", "effect_1_duration": "0",
    })
    return row


def schema_row() -> dict[str, str]:
    row = {column: "" for column in CSV_COLUMNS}
    row.update({
        "record_type": "SCHEMA", "schema_version": SCHEMA_VERSION,
        "character_name": "text; required; max 20 UTF-8 bytes",
        "character_tagline": "max 80 UTF-8 bytes; blank preserves base; <blank> erases",
        "character_description": "max 200 UTF-8 bytes; blank preserves base; <blank> erases",
        "health": "number > 0", "mana": "number >= 0",
        "rage": "number >= 0", "speed": "number >= 0", "slot": "unique integer 1-12",
        "unlock_level": "integer >= 1", "name": "text; required; max 20 UTF-8 bytes",
        "definition": "Attack|Heal|Buff|Debuff|<blank>", "activation_type": "Instant",
        "cast_time": "seconds: 0|0.5|1|2|3|4|5", "cooldown": "seconds: 1|2|3|4|5|10|30|60",
        "range_type": "Self|Melee|Missile|number >= 0",
        "target_area": "Single|Small Area|Large Area|number >= 0",
        "element": "Physical|Light|Dark|Fire|Ice|Water|Electric|Earth",
        "path": "Arc|Ballistic|Straight|Missile|Skybeam",
        "animation": "attack|attackdouble|attackheavy|attackspin|attackheadbutt|cast|castcharge|castswish|castforce",
        "use_weapon_animation": "true|false", "health_cost": "number >= 0",
        "mana_cost": "number >= 0", "rage_cost": "number >= 0",
        "description": "max 200 UTF-8 bytes; <blank> erases; blank preserves base PNG",
    })
    effects = "|".join(EFFECT_TO_INTERNAL)
    for index in range(1, MAX_EFFECTS + 1):
        row[f"effect_{index}_type"] = effects
        row[f"effect_{index}_value"] = "number >= 0"
        row[f"effect_{index}_duration"] = "seconds >= 0; required for timed/control/protect"
    return row


def effect_reference_rows() -> list[dict[str, str]]:
    """Pack all 21 effect definitions into three non-editable CSV reference rows."""
    items = list(EFFECT_HELP.items())
    rows: list[dict[str, str]] = []
    for group_index in range(3):
        row = {column: "" for column in CSV_COLUMNS}
        row.update({
            "record_type": "REFERENCE", "schema_version": SCHEMA_VERSION,
            "name": f"Effect reference {group_index + 1}/3",
            "description": "Do not turn this row into a skill. Use these exact names and rules in SKILL effect triplets.",
        })
        for effect_index, (effect_name, help_values) in enumerate(items[group_index * 7:(group_index + 1) * 7], 1):
            value_help, duration_help, behavior = help_values
            row[f"effect_{effect_index}_type"] = effect_name
            row[f"effect_{effect_index}_value"] = value_help
            row[f"effect_{effect_index}_duration"] = f"{duration_help}; {behavior}"
        rows.append(row)
    return rows


def export_template_csv(path: str | Path) -> None:
    character = {
        "character_name": "New Class", "character_tagline": "", "character_description": "",
        "health": "20", "mana": "10", "rage": "0", "speed": "5",
    }
    _write_document_csv(path, ClassDocument(character, [_blank_skill(slot) for slot in range(1, SKILL_COUNT + 1)]))


def extract_document(card_path: str | Path) -> ClassDocument:
    card = read_card(card_path)
    _ability_start, abilities, _boss_start = _split_abilities(card.record)
    rows = []
    for slot, ability in enumerate(abilities, 1):
        definition = str(_read_scalar(ability, "type"))
        row = {column: "" for column in LEGACY_CSV_COLUMNS}
        row.update({
            "slot": slot,
            "unlock_level": int(_read_scalar(ability, "levelRequirement")),
            "name": str(_read_scalar(ability, "name")),
            "definition": definition if definition else BLANK_SENTINEL,
            "activation_type": str(_read_scalar(ability, "activationType")),
            "cast_time": _format_number(_read_scalar(ability, "castDuration")),
            "cooldown": _format_number(_read_scalar(ability, "cooldown")),
            "range_type": _range_name(str(_read_scalar(ability, "targetType")), float(_read_scalar(ability, "range"))),
            "target_area": _area_name(float(_read_scalar(ability, "effectRadius"))),
            "element": str(_read_scalar(ability, "element")),
            "path": str(_read_scalar(ability, "path")),
            "animation": str(_read_scalar(ability, "userAnimation")),
            "use_weapon_animation": str(_read_scalar(ability, "useWeaponAnimation")),
            "description": str(_read_scalar(ability, "description")),
        })
        for kind, attribute_id, adjustment, _duration, target in _parse_effect_container(ability, "cost"):
            if kind != "attribute" or target != "User" or adjustment > 0 or attribute_id not in (0, 1, 2):
                raise MT2Error(f"Slot {slot} contains an unsupported cost record.")
            row[{0: "health_cost", 1: "mana_cost", 2: "rage_cost"}[attribute_id]] = _format_number(abs(adjustment))
        for cost_column in ("health_cost", "mana_cost", "rage_cost"):
            if row[cost_column] == "":
                row[cost_column] = "0"
        effects = _parse_effect_container(ability, "effect")
        if len(effects) > MAX_EFFECTS:
            raise MT2Error(f"Slot {slot} has {len(effects)} effects; CSV supports {MAX_EFFECTS}.")
        for effect_index, effect in enumerate(effects, 1):
            label, value, duration = _effect_to_csv(effect)
            row[f"effect_{effect_index}_type"] = label
            row[f"effect_{effect_index}_value"] = value
            row[f"effect_{effect_index}_duration"] = duration
        rows.append(row)
    return ClassDocument(extract_character(card.record), rows)


def export_card_csv(card_path: str | Path, csv_path: str | Path) -> None:
    _write_document_csv(csv_path, extract_document(card_path))


def _write_document_csv(path: str | Path, document: ClassDocument) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(schema_row())
        character_row = {column: "" for column in CSV_COLUMNS}
        character_row.update(document.character)
        character_row.update({"record_type": "CHARACTER", "schema_version": SCHEMA_VERSION})
        writer.writerow(character_row)
        writer.writerows(effect_reference_rows())
        for skill in document.skills:
            row = {column: "" for column in CSV_COLUMNS}
            row.update(skill)
            row.update({"record_type": "SKILL", "schema_version": SCHEMA_VERSION})
            writer.writerow(row)


def write_document_csv(path: str | Path, document: ClassDocument) -> None:
    validate_document(document)
    _write_document_csv(path, document)


def read_document_csv(path: str | Path, fallback_character: dict[str, str] | None = None) -> ClassDocument:
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            is_v2 = "record_type" in fieldnames
            optional_v2 = {"character_tagline", "character_description"}
            required = [column for column in CSV_COLUMNS if column not in optional_v2] if is_v2 else LEGACY_CSV_COLUMNS
            missing = [column for column in required if column not in fieldnames]
            if missing:
                raise MT2Error(f"CSV is missing columns: {', '.join(missing)}")
            rows = []
            for row_number, raw_row in enumerate(reader, 2):
                extras = raw_row.pop(None, None)
                if extras is not None:
                    raise MT2Error(
                        f"CSV row {row_number} has {len(extras)} extra column(s), usually caused by a trailing comma. "
                        f"Every row must contain exactly {len(fieldnames)} fields."
                    )
                row: dict[str, str] = {}
                for key, value in raw_row.items():
                    if isinstance(value, list):
                        raise MT2Error(f"CSV row {row_number}, column {key!r} contains an invalid list value.")
                    row[key] = (value or "").strip()
                rows.append(row)
    except OSError as exc:
        raise MT2Error(f"Could not read CSV: {exc}") from exc
    if is_v2:
        schema = [row for row in rows if row.get("record_type", "").casefold() == "schema"]
        characters = [row for row in rows if row.get("record_type", "").casefold() == "character"]
        references = [row for row in rows if row.get("record_type", "").casefold() == "reference"]
        skill_rows = [row for row in rows if row.get("record_type", "").casefold() == "skill"]
        unknown = [row.get("record_type", "") for row in rows if row.get("record_type", "").casefold() not in {"schema", "character", "reference", "skill"}]
        if unknown:
            raise MT2Error(f"CSV contains unknown record_type values: {', '.join(unknown)}")
        if len(schema) != 1 or schema[0].get("schema_version") != SCHEMA_VERSION:
            raise MT2Error(f"CSV must contain one SCHEMA row with schema_version {SCHEMA_VERSION}.")
        if len(characters) != 1:
            raise MT2Error("CSV must contain exactly one CHARACTER row.")
        if len(references) not in {0, 3}:
            raise MT2Error("CSV must contain all three REFERENCE rows or none for older schema-v2 compatibility.")
        character_keys = ("character_name", "character_tagline", "character_description", "health", "mana", "rage", "speed")
        character = {
            key: characters[0].get(key, "") if key in fieldnames else (fallback_character or {}).get(key, "")
            for key in character_keys
        }
    else:
        skill_rows = rows
        character = dict(fallback_character or {})
        if not character:
            raise MT2Error("Legacy skills-only CSV requires a base PNG so character values can be preserved.")
    if len(skill_rows) != SKILL_COUNT:
        raise MT2Error(f"CSV must contain exactly {SKILL_COUNT} SKILL rows, found {len(skill_rows)}.")
    by_slot: dict[int, dict[str, str]] = {}
    for row_number, row in enumerate(skill_rows, 2):
        try:
            slot = int(row["slot"])
        except ValueError as exc:
            raise MT2Error(f"CSV row {row_number}: slot must be an integer.") from exc
        if slot not in range(1, SKILL_COUNT + 1) or slot in by_slot:
            raise MT2Error(f"CSV row {row_number}: slot must be a unique number from 1 to {SKILL_COUNT}.")
        by_slot[slot] = {key: row.get(key, "") for key in LEGACY_CSV_COLUMNS}
    document = ClassDocument(character, [by_slot[slot] for slot in range(1, SKILL_COUNT + 1)])
    validate_document(document)
    return document


def read_skill_csv(path: str | Path) -> list[dict[str, str]]:
    """Backward-compatible reader for v2 CSV files that do not need character metadata."""
    return read_document_csv(path, {
        "character_name": "Preserved", "character_tagline": "", "character_description": "",
        "health": "1", "mana": "0", "rage": "0", "speed": "0",
    }).skills


def validate_document(document: ClassDocument) -> list[str]:
    if len(document.skills) != SKILL_COUNT:
        raise MT2Error(f"Document must contain exactly {SKILL_COUNT} skills.")
    name = document.character.get("character_name", "").strip()
    if not name:
        raise MT2Error("Character name cannot be empty.")
    _validate_utf8_length(name, CHARACTER_NAME_MAX_BYTES, "Character name")
    tagline = document.character.get("character_tagline", "").strip()
    character_description = document.character.get("character_description", "").strip()
    if tagline.casefold() != BLANK_SENTINEL:
        _validate_utf8_length(tagline, CHARACTER_TAGLINE_MAX_BYTES, "Character tagline")
    if character_description.casefold() != BLANK_SENTINEL:
        _validate_utf8_length(character_description, CHARACTER_DESCRIPTION_MAX_BYTES, "Character description")
    health = _number(document.character.get("health", ""), "Character health")
    mana = _number(document.character.get("mana", ""), "Character mana")
    rage = _number(document.character.get("rage", ""), "Character rage")
    speed = _number(document.character.get("speed", ""), "Character speed")
    if health <= 0 or min(mana, rage, speed) < 0:
        raise MT2Error("Health must be greater than zero; mana, rage and speed cannot be negative.")
    warnings: list[str] = []
    seen_slots: set[int] = set()
    for index, row in enumerate(document.skills, 1):
        label = f"Slot {index}"
        try:
            slot = int(row.get("slot", ""))
            level = int(row.get("unlock_level", ""))
        except ValueError as exc:
            raise MT2Error(f"{label}: slot and unlock_level must be integers.") from exc
        if slot not in range(1, SKILL_COUNT + 1) or slot in seen_slots:
            raise MT2Error(f"{label}: slot must be unique from 1 to {SKILL_COUNT}.")
        seen_slots.add(slot)
        ability_name = row.get("name", "").strip()
        if level < 1 or not ability_name:
            raise MT2Error(f"{label}: unlock level must be at least 1 and name is required.")
        _validate_utf8_length(ability_name, ABILITY_NAME_MAX_BYTES, f"{label} ability name")
        ability_description = row.get("description", "").strip()
        if ability_description.casefold() != BLANK_SENTINEL:
            _validate_utf8_length(ability_description, ABILITY_DESCRIPTION_MAX_BYTES, f"{label} ability description")
        definition = row.get("definition", "")
        if definition.casefold() != BLANK_SENTINEL:
            _normalise_choice(definition, DEFINITIONS - {""}, f"{label} definition")
        _normalise_choice(row.get("activation_type", ""), ACTIVATION_TYPES, f"{label} activation_type")
        _normalise_choice(row.get("element", ""), ELEMENTS, f"{label} element")
        raw_path = "Arc" if row.get("path", "").casefold() == "ballistic" else row.get("path", "")
        _normalise_choice(raw_path, PATHS, f"{label} path")
        _normalise_choice(row.get("animation", ""), ANIMATIONS, f"{label} animation")
        _boolean(row.get("use_weapon_animation", ""), f"{label} use_weapon_animation")
        _preset_number(row.get("cast_time", ""), CAST_TIMES, f"{label} cast_time")
        _preset_number(row.get("cooldown", ""), COOLDOWNS, f"{label} cooldown")
        for field in ("health_cost", "mana_cost", "rage_cost"):
            if _number(row.get(field, ""), f"{label} {field}", 0.0) < 0:
                raise MT2Error(f"{label}: {field} cannot be negative.")
        for field, choices in (("range_type", RANGE_VALUES), ("target_area", AREA_VALUES)):
            text = row.get(field, "").strip()
            if text.casefold() not in {value.casefold() for value in choices} and _number(text, f"{label} {field}") < 0:
                raise MT2Error(f"{label}: {field} cannot be negative.")
        seen_keys: set[tuple[str, int]] = set()
        count = 0
        for effect_index in range(1, MAX_EFFECTS + 1):
            effect_type = row.get(f"effect_{effect_index}_type", "")
            value = row.get(f"effect_{effect_index}_value", "")
            duration = row.get(f"effect_{effect_index}_duration", "")
            if not effect_type:
                if value or duration:
                    raise MT2Error(f"{label} effect {effect_index}: type is blank but value or duration is present.")
                continue
            canonical, internal = _effect_from_csv(effect_type, value, duration, f"{label} effect {effect_index}")
            key = (internal[0], internal[1])
            if key in seen_keys:
                raise MT2Error(f"{label}: {canonical} conflicts with another effect using the same MT2 effect slot.")
            seen_keys.add(key)
            count += 1
        if not count:
            raise MT2Error(f"{label}: at least one effect is required.")
        if level != UNLOCK_LEVELS[index - 1]:
            warnings.append(f"Slot {index} uses nonstandard unlock level {level}.")
    return warnings


def _configure_ability(source: bytes, slot_index: int, row: dict[str, str]) -> bytes:
    label = f"Slot {slot_index + 1}"
    try:
        unlock_level = int(row["unlock_level"])
    except ValueError as exc:
        raise MT2Error(f"{label}: unlock_level must be an integer.") from exc
    if unlock_level < 1:
        raise MT2Error(f"{label}: unlock_level must be at least 1.")
    if not row["name"]:
        raise MT2Error(f"{label}: name cannot be empty.")

    definition = "" if row["definition"].casefold() == BLANK_SENTINEL else _normalise_choice(row["definition"], DEFINITIONS - {""}, f"{label} definition")
    activation = _normalise_choice(row["activation_type"], ACTIVATION_TYPES, f"{label} activation_type")
    element = _normalise_choice(row["element"], ELEMENTS, f"{label} element")
    raw_path = row["path"].strip()
    if raw_path.casefold() == "ballistic":
        raw_path = "Arc"
    path = _normalise_choice(raw_path, PATHS, f"{label} path")
    animation = _normalise_choice(row["animation"], ANIMATIONS, f"{label} animation")
    use_weapon = _boolean(row["use_weapon_animation"], f"{label} use_weapon_animation")
    cast_time = _preset_number(row["cast_time"], CAST_TIMES, f"{label} cast_time")
    cooldown = _preset_number(row["cooldown"], COOLDOWNS, f"{label} cooldown")

    range_text = row["range_type"].strip()
    range_lookup = {name.casefold(): (name, value) for name, value in RANGE_VALUES.items()}
    if range_text.casefold() in range_lookup:
        range_name, range_value = range_lookup[range_text.casefold()]
    else:
        range_name, range_value = "Custom", _number(range_text, f"{label} range_type")
    target_type = "Self" if range_name == "Self" else "Any"

    area_text = row["target_area"].strip()
    area_lookup = {name.casefold(): value for name, value in AREA_VALUES.items()}
    effect_radius = area_lookup.get(area_text.casefold())
    if effect_radius is None:
        effect_radius = _number(area_text, f"{label} target_area")
    if range_value < 0 or effect_radius < 0:
        raise MT2Error(f"{label}: range and target radius cannot be negative.")

    costs = []
    for attribute_id, column in enumerate(("health_cost", "mana_cost", "rage_cost")):
        amount = _number(row[column], f"{label} {column}", default=0.0)
        if amount < 0:
            raise MT2Error(f"{label}: {column} cannot be negative.")
        if amount > 0:
            costs.append(_effect_node("attribute", attribute_id, -amount, 0.0, "User"))

    effects = []
    seen_keys: set[tuple[str, int]] = set()
    for index in range(1, MAX_EFFECTS + 1):
        effect_type = row[f"effect_{index}_type"]
        value = row[f"effect_{index}_value"]
        duration = row[f"effect_{index}_duration"]
        if not effect_type:
            if value or duration:
                raise MT2Error(f"{label} effect {index}: type is blank but value or duration is present.")
            continue
        canonical, internal = _effect_from_csv(effect_type, value, duration, f"{label} effect {index}")
        kind, attribute_id, adjustment, seconds, target = internal
        key = (kind, attribute_id)
        if key in seen_keys:
            raise MT2Error(
                f"{label}: {canonical} conflicts with another effect using the same MT2 effect slot. "
                "Damage/Heal, Protect/Weaken, and matching resource pairs cannot coexist."
            )
        seen_keys.add(key)
        effects.append(_effect_node(kind, attribute_id, adjustment, seconds, target))
    if not effects:
        raise MT2Error(f"{label}: at least one effect is required.")

    ability = source
    replacements = [
        ("type", 2, definition),
        ("activationType", 2, activation),
        ("targetType", 2, target_type),
        ("element", 2, element),
        ("path", 2, path),
        ("range", 3, range_value),
        ("cooldown", 3, cooldown),
        ("effectRadius", 3, effect_radius),
        ("displaySlot", 4, slot_index),
        ("userAnimation", 2, animation),
        ("useWeaponAnimation", 2, use_weapon),
        ("castDuration", 3, cast_time),
        ("levelRequirement", 4, unlock_level),
        ("name", 2, row["name"]),
    ]
    if row["description"]:
        description = "" if row["description"].casefold() == BLANK_SENTINEL else row["description"]
        replacements.append(("description", 2, description))
    for field, tag, value in replacements:
        ability = _replace_scalar(ability, field, tag, value)

    cost_start = ability.find(signature("cost"))
    effect_start = ability.find(signature("effect"), cost_start + 1)
    display_slot = ability.find(signature("displaySlot"), effect_start)
    if not (0 <= cost_start < effect_start < display_slot):
        raise MT2Error(f"{label}: ability containers are not in the expected order.")
    return ability[:cost_start] + _composite("cost", costs) + _composite("effect", effects) + ability[display_slot:]


def build_card_from_document(base_png: str | Path, document: ClassDocument, output_png: str | Path) -> dict[str, int]:
    card = read_card(base_png)
    validate_document(document)
    ability_start, source_abilities, boss_start = _split_abilities(card.record)
    new_abilities = [
        _configure_ability(source, slot_index, row)
        for slot_index, (source, row) in enumerate(zip(source_abilities, document.skills))
    ]
    new_record = card.record[:ability_start] + _composite("ability", new_abilities) + card.record[boss_start:]
    new_record = _configure_character(new_record, document.character)
    write_card(card, new_record, output_png)
    verified = read_card(output_png)
    return {
        "record_bytes": len(new_record),
        "compressed_bytes": len(verified.compressed),
        "declared_bytes": verified.declared_length,
    }


def build_card_from_csv(base_png: str | Path, csv_path: str | Path, output_png: str | Path) -> dict[str, int]:
    base = read_card(base_png)
    document = read_document_csv(csv_path, extract_character(base.record))
    return build_card_from_document(base_png, document, output_png)


def validate_card(path: str | Path) -> dict[str, int | bool]:
    card = read_card(path)
    _ability_start, abilities, _boss_start = _split_abilities(card.record)
    return {
        "record_bytes": len(card.record),
        "compressed_bytes": len(card.compressed),
        "declared_bytes": card.declared_length,
        "header_matches_payload": card.declared_length == len(card.compressed),
        "skills": len(abilities),
    }
