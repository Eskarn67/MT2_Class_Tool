# MMORPG Tycoon 2 Class Editor

A Windows desktop editor for the character data hidden inside MMORPG Tycoon 2 class-card PNG files. It keeps all 12 skills visible in one window and supports a self-describing CSV designed for safe collaboration with an LLM.

The editor changes the class name, tagline, description, base health, mana, rage, movement speed, and supported skill fields. The base PNG's model, colours, scales, costume and ability icons are preserved.

Latest version <https://github.com/Eskarn67/MT2_Class_Tool/blob/main/dist/MT2ClassTool.exe>


## Build the standalone Windows EXE

1. Install 64-bit Python 3 from <https://www.python.org/downloads/windows/> and enable **Add Python to PATH**.
2. Double-click `build_windows.bat`.
3. Find the standalone app at `dist\MT2ClassTool.exe`.

Python is needed only to build the EXE. The resulting executable includes Python, Pillow and Tk and can run on another Windows machine without Python installed. `run_from_source.bat` starts the editor directly for development.

## Recommended workflow

1. Export a known-good 280x500 character-class PNG from MMORPG Tycoon 2.
2. Back up your game save and that PNG.
3. Open the PNG with **Open Base PNG**. The editor loads the character and all 12 skills.
4. Edit directly in the window, or click **Export CSV**.
5. To use an LLM, click **Copy LLM Prompt** and give the LLM both the prompt and exported CSV.
6. Import the returned CSV and click **Validate All**.
7. Click **Build & Verify PNG**, choose a new filename, and import that new PNG in game.

Never overwrite the base card. The editor blocks that operation.

## Editor layout

- **Character:** name, card tagline, longer class description, health, mana, rage and speed.
- **All 12 Skills:** a permanent overview showing slot, level, name, definition, cast, cooldown, costs and effect summary.
- **Selected Skill:** mechanics, costs, visuals, eight effect positions and description on one scrollable page—no three-tab modal.
- **Dark/light mode:** dark mode is the default; the top-right toggle is remembered between launches.
- **Duplicate to Next:** copies the selected ability while keeping the next slot and its unlock level.

## Self-describing CSV v2

The first column is `record_type`. Every CSV contains:

- one `SCHEMA` row describing valid values and constraints in the same columns an LLM will edit;
- one `CHARACTER` row containing name, tagline, description, health, mana, rage and speed;
- three `REFERENCE` rows explaining every effect's exact dropdown name, value meaning, duration rule and behavior;
- exactly twelve `SKILL` rows with unique slots 1–12.

The schema version is `2`. The editor can still import the earlier skills-only CSV when a base PNG is already open, so character values can be preserved safely.

`character_tagline` is the short line shown below the class name. `character_description` is the larger class-role/flavor paragraph. Leaving either blank preserves the base PNG's current value; use `<blank>` to deliberately erase it. Older schema-v2 CSVs without these two columns remain importable when a base PNG is open.

Confirmed game-safe text limits are measured in UTF-8 bytes: character name 20, character tagline 80, character description 200, and each skill name 20. The tool also applies a 200-byte safety limit to each skill description. Ordinary English letters use one byte each; accented and non-Latin characters may use more. The editor rejects an overlong value before writing a PNG.

`LLM_GUIDE.md` is a standalone reference that can be supplied to an LLM alongside the CSV. The same short reusable prompt is available from **Copy LLM Prompt** in the editor.

### Skill fields

- `unlock_level`: integer at least 1; normal sequence is `1, 1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20`.
- `name`: required skill/ability name, maximum 20 UTF-8 bytes.
- `definition`: `Attack`, `Heal`, `Buff`, `Debuff`, or `<blank>`.
- `activation_type`: confirmed value `Instant`.
- `cast_time`: confirmed presets `0`, `0.5`, `1`, `2`, `3`, `4`, or `5` seconds.
- `cooldown`: confirmed presets `1`, `2`, `3`, `4`, `5`, `10`, `30`, or `60` seconds.
- `range_type`: `Self`, `Melee`, `Missile`, or a nonnegative numeric range.
- `target_area`: `Single`, `Small Area`, `Large Area`, or a nonnegative numeric radius. The named radii are 0, 5 and 15.
- `element` (shown as **Effect type** in game): `Physical`, `Light`, `Dark`, `Fire`, `Ice`, `Water`, `Electric`, `Earth`.
- `path`: `Arc`, `Ballistic` (alias for Arc), `Straight`, `Missile`, `Skybeam`.
- `animation`: `attack`, `attackdouble`, `attackheavy`, `attackspin`, `attackheadbutt`, `cast`, `castcharge`, `castswish`, `castforce`.
- `use_weapon_animation`: `true` or `false`.
- `health_cost`, `mana_cost`, `rage_cost`: nonnegative amounts; the encoder stores them as negative effects on the user.
- `description`: maximum 200 UTF-8 bytes; blank preserves the base ability's description; `<blank>` deliberately erases it.

Each of the eight effect positions has `effect_N_type`, `effect_N_value`, and `effect_N_duration`.

Supported effects are Damage, Heal, Damage Over Time, Heal Over Time, Drain Mana, Charge Mana, Drain Mana Over Time, Charge Mana Over Time, Reduce Rage, Generate Rage, Drain Rage Over Time, Generate Rage Over Time, Siphon Health, Siphon Mana, Siphon Rage, Slow, Root In Place, Stun, Protect, Weaken and Taunt.

Durations greater than zero are required for over-time effects, Slow, Root In Place, Stun, Taunt, Protect and Weaken.

The three `REFERENCE` rows are instructions, not abilities. Each populated effect triplet contains an exact dropdown name, an explanation of the value field, and the duration requirement plus behavior. LLMs should preserve these rows unchanged and create effects only inside `SKILL` rows.

## Critical conflict rule

The game stores UI opposites using the same internal `(effect type, attribute)` and distinguishes them only by sign. Never put both members of one pair on a skill:

- Damage / Heal
- Damage Over Time / Heal Over Time
- Drain Mana / Charge Mana
- Drain Mana Over Time / Charge Mana Over Time
- Reduce Rage / Generate Rage
- Drain Rage Over Time / Generate Rage Over Time
- Protect / Weaken

The editor rejects these conflicts before touching an output PNG.

## PNG safety

The game importer can crash on malformed embedded data. This editor:

- requires a game-exported 280x500 PNG carrier;
- edits the existing binary `RecordV2` structure instead of inventing a new one;
- preserves unsupported/model/icon data byte-for-byte;
- recompresses the payload and updates its two-byte length header;
- rereads the finished PNG and verifies both the full record and declared compressed length before reporting success.

Values can be structurally valid but still make poor gameplay. Prefer combinations and ranges already accepted by the in-game editor, and test new cards with backups available.

## Command line

```bat
py -3 mt2_cli.py template MT2_Class_Template.csv
py -3 mt2_cli.py export BaseCard.png class.csv
py -3 mt2_cli.py build BaseCard.png class.csv NewCard.png
py -3 mt2_cli.py validate NewCard.png
```
