# Instructions for an LLM editing an MT2 class CSV

The CSV is the complete editable character-class brief for the companion MT2 Class Editor. Read the `SCHEMA` row before changing anything: each cell states the values or constraint allowed in that column.

## Required output contract

1. Return CSV, not prose.
2. Preserve the exact header and `schema_version` value `2`.
3. Preserve exactly one `SCHEMA` row, one `CHARACTER` row, three `REFERENCE` rows and twelve `SKILL` rows.
4. Keep skill slots unique and numbered 1 through 12.
5. Put character name, tagline, description, health, mana, rage and speed only on the `CHARACTER` row.
6. Put ability data only on `SKILL` rows.
7. Use only enum values listed in the `SCHEMA` row. Do not invent spelling variants.
8. Use nonnegative numeric values. Timed/control effects and Protect/Weaken need a duration greater than zero.
9. Every skill needs at least one effect.
10. Keep unused effect triplets completely empty.

Cast time and cooldown are preset fields, not arbitrary numbers. Use only the values listed in their `SCHEMA` cells.

## How to create effects

Read the three `REFERENCE` rows in the CSV. Together they list every effect available in the editor dropdown. Each populated reference triplet contains:

- `effect_N_type`: the exact dropdown spelling to copy into a `SKILL` row;
- `effect_N_value`: what the number represents;
- `effect_N_duration`: whether duration is `0` or greater than zero, followed by the effect's behavior.

To add effects to a skill, start at `effect_1_type/value/duration` and use consecutive triplets. Do not put effect data in `CHARACTER`, `SCHEMA`, or `REFERENCE` rows. Keep all three cells empty for an unused effect position.

- Immediate Damage, Heal, Mana and Rage changes use their resource amount and duration `0`.
- Over-Time effects use the amount entered over a duration greater than zero.
- Siphons use a resource amount and duration `0`; they drain the target and return that resource to the user.
- Slow has no percentage value: use `0` and a duration greater than zero.
- Root In Place, Stun and Taunt use `0` and a duration greater than zero.
- Protect and Weaken use a percentage value and a duration greater than zero.
- Skill costs are separate: use positive numbers in `health_cost`, `mana_cost`, or `rage_cost`; they are charged to the user.

## Effects that cannot share one skill

These pairs map to the same internal MT2 effect identifier and differ only by sign. Never include both members of a pair on one skill:

- Damage and Heal
- Damage Over Time and Heal Over Time
- Drain Mana and Charge Mana
- Drain Mana Over Time and Charge Mana Over Time
- Reduce Rage and Generate Rage
- Drain Rage Over Time and Generate Rage Over Time
- Protect and Weaken

Different pairs can coexist. For example, Damage plus Stun is valid, and Heal plus Protect is valid.

## Preserve-versus-erase behavior

- `character_tagline` is the short line beneath the class name; `character_description` is the longer class-role/flavor paragraph.
- Text limits are measured in UTF-8 bytes: `character_name` 20, `character_tagline` 80, `character_description` 200, every SKILL `name` 20, and every SKILL `description` 200. ASCII characters use one byte; do not assume one character always equals one byte.
- A blank character tagline or description preserves the value in the base PNG; `<blank>` deliberately erases it.
- A blank skill `description` preserves the description already in the base PNG.
- The literal value `<blank>` deliberately stores an empty description or definition.
- Model, colours, scales, costume and icons do not exist in this CSV and are preserved from the base PNG by the editor.

## Reusable prompt

> Create or edit this MMORPG Tycoon 2 character class using only values allowed by the SCHEMA row. Fill the CHARACTER row, including character_name, character_tagline, character_description, health, mana, rage, and speed. Respect these UTF-8 byte limits: character_name 20, character_tagline 80, character_description 200, every SKILL name 20, and every SKILL description 200. Read and preserve all three REFERENCE rows: they define every effect name, what its value means, its duration rule, and its behavior. Preserve the exact CSV headers, one SCHEMA row, one CHARACTER row, three REFERENCE rows, all 12 SKILL rows, unique slot numbers 1-12, and schema_version 2. Put effects only into SKILL effect_N_type/value/duration triplets. Never combine either member of these pairs on one skill: Damage/Heal; Damage Over Time/Heal Over Time; Drain Mana/Charge Mana; Drain Mana Over Time/Charge Mana Over Time; Reduce Rage/Generate Rage; Drain Rage Over Time/Generate Rage Over Time; Protect/Weaken. Return only the complete CSV in a code block, with no commentary.
