from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mt2_core import (  # noqa: E402
    ABILITY_DESCRIPTION_MAX_BYTES, ABILITY_NAME_MAX_BYTES, ACTIVATION_TYPES, ANIMATIONS,
    AREA_VALUES, BLANK_SENTINEL, CAST_TIMES, CHARACTER_DESCRIPTION_MAX_BYTES,
    CHARACTER_NAME_MAX_BYTES, CHARACTER_TAGLINE_MAX_BYTES, COOLDOWNS, ClassDocument,
    DEFINITIONS, EFFECT_TO_INTERNAL, ELEMENTS, LEGACY_CSV_COLUMNS, MAX_EFFECTS,
    MT2Error, PATHS, RANGE_VALUES, SKILL_COUNT, build_card_from_document,
    export_template_csv, extract_document, read_document_csv, validate_card,
    validate_document, write_document_csv,
)

DARK = {"window": "#091722", "panel": "#10283A", "input": "#081D2C", "border": "#176A9E", "accent": "#1597D4", "selected": "#167CB8", "text": "#E6F2FA", "muted": "#9FB8C8"}
LIGHT = {"window": "#EEF5F8", "panel": "#FFFFFF", "input": "#F7FBFD", "border": "#7BAFCB", "accent": "#087CB6", "selected": "#CBEAF8", "text": "#102533", "muted": "#526B78"}


def _settings_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "MT2ClassTool" / "settings.json"


class MT2ClassTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MMORPG Tycoon 2 Class Editor")
        self.geometry("1440x880")
        self.minsize(1120, 720)
        self.base_png = ""
        self.skills: list[dict[str, str]] = []
        self.current_slot: int | None = None
        self.theme_name = self._load_theme()
        self.status = tk.StringVar(value="Open a known-good MT2 class PNG, or import a schema-v2 CSV.")
        self.char_vars = {name: tk.StringVar() for name in (
            "character_name", "character_tagline", "character_description", "health", "mana", "rage", "speed"
        )}
        self.skill_vars: dict[str, tk.Variable] = {}
        self.effect_vars: list[tuple[tk.StringVar, tk.StringVar, tk.StringVar]] = []
        self._build_ui()
        self._apply_theme()

    def _load_theme(self) -> str:
        try:
            return json.loads(_settings_path().read_text(encoding="utf-8")).get("theme", "dark")
        except (OSError, ValueError):
            return "dark"

    def _save_theme(self):
        try:
            path = _settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"theme": self.theme_name}), encoding="utf-8")
        except OSError:
            pass

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(12, 9))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="MT2 Class Editor", style="Title.TLabel").pack(side="left", padx=(0, 18))
        for text, command in (("Open Base PNG", self.open_base), ("Import CSV", self.import_csv), ("Export CSV", self.export_csv), ("Blank Template", self.export_blank), ("Copy LLM Prompt", self.copy_llm_prompt), ("Build & Verify PNG", self.build_png)):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=3)
        self.theme_button = ttk.Button(toolbar, command=self.toggle_theme)
        self.theme_button.pack(side="right")

        general = ttk.LabelFrame(self, text="Character", padding=10)
        general.pack(fill="x", padx=12, pady=(0, 8))
        labels = (("character_name", f"Name (max {CHARACTER_NAME_MAX_BYTES} bytes)", 26), ("health", "Health", 9), ("mana", "Mana", 9), ("rage", "Rage", 9), ("speed", "Speed", 9))
        for column, (key, label, width) in enumerate(labels):
            ttk.Label(general, text=label).grid(row=0, column=column * 2, padx=(0, 5), sticky="w")
            ttk.Entry(general, textvariable=self.char_vars[key], width=width).grid(row=0, column=column * 2 + 1, padx=(0, 16), sticky="ew")
        general.columnconfigure(1, weight=1)
        ttk.Label(general, text=f"Tagline (max {CHARACTER_TAGLINE_MAX_BYTES} bytes)").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(8, 3))
        ttk.Entry(general, textvariable=self.char_vars["character_tagline"]).grid(row=1, column=1, columnspan=9, sticky="ew", pady=(8, 3))
        ttk.Label(general, text=f"Description (max {CHARACTER_DESCRIPTION_MAX_BYTES} bytes)").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=3)
        self.character_description = tk.Text(general, height=3, wrap="word", undo=True)
        self.character_description.grid(row=2, column=1, columnspan=9, sticky="ew", pady=3)
        ttk.Label(general, text=f"Blank preserves the base card. Use {BLANK_SENTINEL} to erase either text field.", style="Muted.TLabel").grid(row=3, column=0, columnspan=10, sticky="w", pady=(3, 0))
        self.base_label = ttk.Label(general, text="No base PNG loaded", style="Muted.TLabel")
        self.base_label.grid(row=4, column=0, columnspan=10, sticky="w", pady=(5, 0))

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        left, right = ttk.Frame(panes, padding=(0, 0, 8, 0)), ttk.Frame(panes)
        panes.add(left, weight=5)
        panes.add(right, weight=7)
        ttk.Label(left, text="All 12 Skills", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        columns = ("slot", "level", "name", "definition", "cast", "cooldown", "cost", "effects")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=16)
        headings = {"slot": "#", "level": "Lvl", "name": "Name", "definition": "Type", "cast": "Cast", "cooldown": "CD", "cost": "Cost", "effects": "Effects"}
        widths = {"slot": 34, "level": 42, "name": 150, "definition": 68, "cast": 48, "cooldown": 48, "cost": 88, "effects": 260}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=30, stretch=column in {"name", "effects"})
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._select_skill)
        nav = ttk.Frame(left)
        nav.pack(fill="x", pady=(7, 0))
        ttk.Button(nav, text="Previous", command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(nav, text="Next", command=lambda: self._move(1)).pack(side="left", padx=5)
        ttk.Button(nav, text="Duplicate to Next", command=self._duplicate).pack(side="left", padx=5)
        ttk.Button(nav, text="Validate All", command=self.validate_all).pack(side="right")

        ttk.Label(right, text="Selected Skill", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        canvas = tk.Canvas(right, highlightthickness=0)
        scroll = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.editor = ttk.Frame(canvas, padding=(2, 0, 8, 8))
        editor_window = canvas.create_window((0, 0), window=self.editor, anchor="nw")
        self.editor.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(editor_window, width=e.width))
        self.editor_canvas = canvas
        self._build_skill_editor()

        status = ttk.Frame(self, padding=(12, 5))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status).pack(side="left")
        ttk.Label(status, text="Model, colours, scales and icons are preserved from the base PNG.", style="Muted.TLabel").pack(side="right")

    def _build_skill_editor(self):
        fields = [
            ("name", f"Skill name (max {ABILITY_NAME_MAX_BYTES} bytes)", "entry", None), ("unlock_level", "Unlock level", "entry", None),
            ("definition", "Definition", "combo", sorted(DEFINITIONS - {""}) + [BLANK_SENTINEL]), ("activation_type", "Activation", "combo", sorted(ACTIVATION_TYPES)),
            ("cast_time", "Cast time (sec)", "combo", [str(int(v)) if v.is_integer() else str(v) for v in CAST_TIMES]),
            ("cooldown", "Cooldown (sec)", "combo", [str(int(v)) if v.is_integer() else str(v) for v in COOLDOWNS]),
            ("range_type", "Range", "combo", list(RANGE_VALUES)), ("target_area", "Target area", "combo", list(AREA_VALUES)),
            ("health_cost", "Health cost", "entry", None), ("mana_cost", "Mana cost", "entry", None),
            ("rage_cost", "Rage cost", "entry", None), ("element", "Effect type", "combo", sorted(ELEMENTS)),
            ("path", "Path", "combo", sorted(PATHS)), ("animation", "Animation", "combo", sorted(ANIMATIONS)),
        ]
        mechanics = ttk.LabelFrame(self.editor, text="Mechanics, costs and visuals", padding=9)
        mechanics.pack(fill="x")
        for index, (key, label, kind, values) in enumerate(fields):
            row, pair = divmod(index, 2)
            column = pair * 2
            ttk.Label(mechanics, text=label).grid(row=row, column=column, sticky="w", padx=(0, 5), pady=3)
            variable = tk.StringVar()
            self.skill_vars[key] = variable
            widget = ttk.Combobox(mechanics, textvariable=variable, values=values, state="readonly", width=22) if kind == "combo" else ttk.Entry(mechanics, textvariable=variable, width=24)
            widget.grid(row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=3)
        mechanics.columnconfigure(1, weight=1)
        mechanics.columnconfigure(3, weight=1)
        self.weapon_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(mechanics, text="Use weapon animation", variable=self.weapon_var).grid(row=(len(fields) + 1) // 2, column=0, columnspan=4, sticky="w", pady=(5, 0))

        effects = ttk.LabelFrame(self.editor, text="Effects on target — game conflict pairs cannot coexist", padding=9)
        effects.pack(fill="x", pady=8)
        for column, text in enumerate(("#", "Effect", "Value", "Duration (sec)")):
            ttk.Label(effects, text=text, style="Muted.TLabel").grid(row=0, column=column, sticky="w", padx=4)
        choices = [""] + list(EFFECT_TO_INTERNAL)
        for index in range(MAX_EFFECTS):
            variables = (tk.StringVar(), tk.StringVar(), tk.StringVar())
            self.effect_vars.append(variables)
            ttk.Label(effects, text=str(index + 1)).grid(row=index + 1, column=0, padx=4, pady=2)
            ttk.Combobox(effects, textvariable=variables[0], values=choices, state="readonly", width=27).grid(row=index + 1, column=1, sticky="ew", padx=4, pady=2)
            ttk.Entry(effects, textvariable=variables[1], width=12).grid(row=index + 1, column=2, sticky="ew", padx=4, pady=2)
            ttk.Entry(effects, textvariable=variables[2], width=14).grid(row=index + 1, column=3, sticky="ew", padx=4, pady=2)
        effects.columnconfigure(1, weight=1)

        flavor = ttk.LabelFrame(self.editor, text="Skill description / flavor", padding=9)
        flavor.pack(fill="both", expand=True)
        self.description = tk.Text(flavor, height=4, wrap="word", undo=True)
        self.description.pack(fill="both", expand=True)
        ttk.Label(flavor, text=f"Maximum {ABILITY_DESCRIPTION_MAX_BYTES} UTF-8 bytes. Blank preserves the base skill description; use <blank> to erase it.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

    def _apply_theme(self):
        p = DARK if self.theme_name == "dark" else LIGHT
        self.configure(bg=p["window"])
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure(".", background=p["window"], foreground=p["text"], fieldbackground=p["input"], bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"], font=("Segoe UI", 9))
        style.configure("TFrame", background=p["window"])
        style.configure("TLabelframe", background=p["panel"], bordercolor=p["border"])
        style.configure("TLabelframe.Label", background=p["panel"], foreground=p["text"], font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background=p["window"], foreground=p["text"])
        style.configure("Muted.TLabel", foreground=p["muted"])
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"), foreground=p["accent"])
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), foreground=p["text"])
        style.configure("TButton", background=p["panel"], foreground=p["text"], bordercolor=p["border"], padding=(8, 5))
        style.map("TButton", background=[("active", p["accent"])], foreground=[("active", "#FFFFFF")])
        style.configure("TEntry", fieldbackground=p["input"], foreground=p["text"], insertcolor=p["text"])
        style.configure("TCombobox", fieldbackground=p["input"], foreground=p["text"], arrowcolor=p["text"])
        style.map("TCombobox", fieldbackground=[("readonly", p["input"])], foreground=[("readonly", p["text"])])
        style.configure("Treeview", background=p["input"], fieldbackground=p["input"], foreground=p["text"], rowheight=27)
        style.configure("Treeview.Heading", background=p["panel"], foreground=p["text"])
        style.map("Treeview", background=[("selected", p["selected"])], foreground=[("selected", "#FFFFFF" if self.theme_name == "dark" else p["text"])])
        self.editor_canvas.configure(bg=p["window"])
        self.description.configure(bg=p["input"], fg=p["text"], insertbackground=p["text"], relief="flat", highlightthickness=1, highlightbackground=p["border"])
        self.character_description.configure(bg=p["input"], fg=p["text"], insertbackground=p["text"], relief="flat", highlightthickness=1, highlightbackground=p["border"])
        self.theme_button.configure(text="Light mode" if self.theme_name == "dark" else "Dark mode")

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self._apply_theme(); self._save_theme()

    def _set_document(self, document: ClassDocument):
        self._flush_skill()
        self.skills = [{key: row.get(key, "") for key in LEGACY_CSV_COLUMNS} for row in document.skills]
        for key, variable in self.char_vars.items():
            if key != "character_description": variable.set(document.character.get(key, ""))
        self.character_description.delete("1.0", "end")
        self.character_description.insert("1.0", document.character.get("character_description", ""))
        self.current_slot = None
        self._refresh_tree()
        if self.skills: self.tree.selection_set("1"); self.tree.focus("1")

    def _document(self) -> ClassDocument:
        self._flush_skill()
        character = {key: variable.get().strip() for key, variable in self.char_vars.items() if key != "character_description"}
        character["character_description"] = self.character_description.get("1.0", "end-1c").strip()
        return ClassDocument(character, self.skills)

    def _refresh_tree(self):
        selected = str(self.current_slot or 1)
        for item in self.tree.get_children(): self.tree.delete(item)
        for row in self.skills:
            effects = ", ".join(row.get(f"effect_{i}_type", "") for i in range(1, MAX_EFFECTS + 1) if row.get(f"effect_{i}_type", "")) or "MISSING"
            costs = [f"{label} {row.get(key, '0')}" for label, key in (("H", "health_cost"), ("M", "mana_cost"), ("R", "rage_cost")) if row.get(key, "0") not in {"", "0", "0.0"}]
            self.tree.insert("", "end", iid=row["slot"], values=(row["slot"], row["unlock_level"], row["name"], row["definition"], row["cast_time"], row["cooldown"], ", ".join(costs) or "None", effects))
        if self.tree.exists(selected): self.tree.selection_set(selected)

    def _select_skill(self, _event=None):
        selection = self.tree.selection()
        if not selection: return
        new_slot = int(selection[0])
        if self.current_slot == new_slot: return
        self._flush_skill(); self.current_slot = new_slot
        row = self.skills[new_slot - 1]
        for key, variable in self.skill_vars.items(): variable.set(row.get(key, ""))
        self.weapon_var.set(row.get("use_weapon_animation", "true").casefold() in {"true", "yes", "1"})
        for index, variables in enumerate(self.effect_vars, 1):
            variables[0].set(row.get(f"effect_{index}_type", "")); variables[1].set(row.get(f"effect_{index}_value", "")); variables[2].set(row.get(f"effect_{index}_duration", ""))
        self.description.delete("1.0", "end"); self.description.insert("1.0", row.get("description", ""))
        self.status.set(f"Editing skill {new_slot} of {SKILL_COUNT}.")

    def _flush_skill(self):
        if self.current_slot is None or not self.skills: return
        row = self.skills[self.current_slot - 1]
        for key, variable in self.skill_vars.items(): row[key] = str(variable.get()).strip()
        row["use_weapon_animation"] = "true" if self.weapon_var.get() else "false"
        for index, variables in enumerate(self.effect_vars, 1):
            row[f"effect_{index}_type"] = variables[0].get().strip(); row[f"effect_{index}_value"] = variables[1].get().strip(); row[f"effect_{index}_duration"] = variables[2].get().strip()
        row["description"] = self.description.get("1.0", "end-1c")
        if self.tree.exists(str(self.current_slot)):
            effects = ", ".join(row[f"effect_{i}_type"] for i in range(1, MAX_EFFECTS + 1) if row[f"effect_{i}_type"])
            costs = [f"{label} {row[key]}" for label, key in (("H", "health_cost"), ("M", "mana_cost"), ("R", "rage_cost")) if row[key] not in {"", "0", "0.0"}]
            self.tree.item(str(self.current_slot), values=(row["slot"], row["unlock_level"], row["name"], row["definition"], row["cast_time"], row["cooldown"], ", ".join(costs) or "None", effects or "MISSING"))

    def _move(self, delta: int):
        if not self.skills: return
        slot = max(1, min(SKILL_COUNT, (self.current_slot or 1) + delta))
        self.tree.selection_set(str(slot)); self.tree.focus(str(slot)); self.tree.see(str(slot))

    def _duplicate(self):
        if not self.current_slot or self.current_slot >= SKILL_COUNT: return
        self._flush_skill(); target_slot = self.current_slot + 1
        source = dict(self.skills[self.current_slot - 1]); source["slot"] = str(target_slot); source["unlock_level"] = self.skills[target_slot - 1]["unlock_level"]; source["name"] += " Copy"
        self.skills[target_slot - 1] = source; self._refresh_tree(); self.tree.selection_set(str(target_slot))

    def open_base(self):
        path = filedialog.askopenfilename(title="Open a known-good MT2 class card", filetypes=[("PNG files", "*.png")])
        if path: self._run(lambda: self._load_base(path), "Base PNG loaded and decoded.")

    def _load_base(self, path: str):
        info = validate_card(path)
        if not info["header_matches_payload"]: raise MT2Error("Base PNG has a mismatched compressed-payload header and is unsafe to use.")
        self.base_png = path; self.base_label.configure(text=f"Base: {path}"); self._set_document(extract_document(path)); return info

    def import_csv(self):
        path = filedialog.askopenfilename(title="Import class CSV", filetypes=[("CSV files", "*.csv")])
        if not path: return
        fallback = extract_document(self.base_png).character if self.base_png else None
        self._run(lambda: self._set_document(read_document_csv(path, fallback)), "CSV imported and validated.")

    def export_csv(self):
        if not self.skills: messagebox.showwarning("MT2 Class Editor", "Open a base PNG or import a CSV first."); return
        path = filedialog.asksaveasfilename(title="Export self-describing class CSV", defaultextension=".csv", initialfile="MT2_Class.csv", filetypes=[("CSV files", "*.csv")])
        if path: self._run(lambda: write_document_csv(path, self._document()), f"Exported self-describing CSV: {path}")

    def export_blank(self):
        path = filedialog.asksaveasfilename(title="Export blank schema-v2 template", defaultextension=".csv", initialfile="MT2_Class_Template.csv", filetypes=[("CSV files", "*.csv")])
        if path: self._run(lambda: export_template_csv(path), f"Exported blank template: {path}")

    def validate_all(self):
        if not self.skills: messagebox.showwarning("MT2 Class Editor", "Nothing to validate yet."); return
        def action():
            warnings = validate_document(self._document())
            return "Valid. " + ("Warnings: " + " ".join(warnings) if warnings else "No warnings.")
        self._run(action, "All character and skill fields passed validation.")

    def build_png(self):
        if not self.base_png: messagebox.showwarning("MT2 Class Editor", "Open a known-good base PNG first. Its model and icons will be preserved."); return
        path = filedialog.asksaveasfilename(title="Build MT2 class PNG", defaultextension=".png", initialfile=f"{self.char_vars['character_name'].get() or 'MT2_Class'}.png", filetypes=[("PNG files", "*.png")])
        if not path: return
        if Path(path).resolve() == Path(self.base_png).resolve(): messagebox.showerror("MT2 Class Editor", "Choose a new filename; the base PNG will not be overwritten."); return
        self._run(lambda: build_card_from_document(self.base_png, self._document(), path), f"Built, reread and verified working PNG: {path}")

    def copy_llm_prompt(self):
        prompt = "Create or edit this MMORPG Tycoon 2 character class using only values allowed by the SCHEMA row. Fill the CHARACTER row, including character_name, character_tagline, character_description, health, mana, rage, and speed. Respect these UTF-8 byte limits: character_name 20, character_tagline 80, character_description 200, every SKILL name 20, and every SKILL description 200. Read and preserve all three REFERENCE rows: they define every effect name, what its value means, its duration rule, and its behavior. Preserve the exact CSV headers, one SCHEMA row, one CHARACTER row, three REFERENCE rows, all 12 SKILL rows, unique slot numbers 1-12, and schema_version 2. Put effects only into SKILL effect_N_type/value/duration triplets. Never combine either member of these pairs on one skill: Damage/Heal; Damage Over Time/Heal Over Time; Drain Mana/Charge Mana; Drain Mana Over Time/Charge Mana Over Time; Reduce Rage/Generate Rage; Drain Rage Over Time/Generate Rage Over Time; Protect/Weaken. Return only the complete CSV in a code block, with no commentary."
        self.clipboard_clear(); self.clipboard_append(prompt); self.status.set("LLM instructions copied. Export the CSV and provide both to the LLM.")

    def _run(self, action, success: str):
        try: result = action()
        except MT2Error as exc: self.status.set(f"Error: {exc}"); messagebox.showerror("MT2 Class Editor", str(exc)); return
        except Exception as exc: self.status.set("Unexpected error; no PNG was accepted as complete."); messagebox.showerror("MT2 Class Editor", f"Unexpected error:\n{exc}"); return
        self.status.set(success)
        if result and isinstance(result, str): messagebox.showinfo("MT2 Class Editor", result)


if __name__ == "__main__":
    MT2ClassTool().mainloop()
