from __future__ import annotations

import argparse
import json

from mt2_core import build_card_from_csv, export_card_csv, export_template_csv, validate_card


def main():
    parser = argparse.ArgumentParser(description="MMORPG Tycoon 2 class-card CSV tool")
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("template", help="Export a blank 12-skill CSV template")
    template.add_argument("csv")

    export = commands.add_parser("export", help="Export the 12 skills in a PNG to CSV")
    export.add_argument("png")
    export.add_argument("csv")

    build = commands.add_parser("build", help="Build a new PNG from a base card and CSV")
    build.add_argument("base_png")
    build.add_argument("csv")
    build.add_argument("output_png")

    validate = commands.add_parser("validate", help="Validate a class PNG and payload header")
    validate.add_argument("png")

    args = parser.parse_args()
    if args.command == "template":
        export_template_csv(args.csv)
        print(f"Created {args.csv}")
    elif args.command == "export":
        export_card_csv(args.png, args.csv)
        print(f"Created {args.csv}")
    elif args.command == "build":
        print(json.dumps(build_card_from_csv(args.base_png, args.csv, args.output_png), indent=2))
    elif args.command == "validate":
        print(json.dumps(validate_card(args.png), indent=2))


if __name__ == "__main__":
    main()
