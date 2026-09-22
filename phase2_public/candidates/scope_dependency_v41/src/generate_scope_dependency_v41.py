"""Generate reviewable schema/prompt mirrors; default is drift check only."""
from pathlib import Path
import argparse
from scope_dependency_v41_schema import render_schema
from scope_dependency_v41_prompt import build_addendum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    outputs = {
        root / "schemas/scope_dependency_v41.schema.json": render_schema() + "\n",
        root / "prompts/scope_dependency_v41_candidate.md": build_addendum().strip() + "\n",
    }
    for path, content in outputs.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Generated contract drift: " + str(path.relative_to(root)))
    print("Schema and prompt mirrors match the executable protocol.")


if __name__ == "__main__":
    main()
