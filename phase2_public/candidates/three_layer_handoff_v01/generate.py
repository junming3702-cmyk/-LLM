"""Generate protocol documentation from the same specification used by gate."""
import argparse
import json
from pathlib import Path
from spec import SPEC, render_prompt

def generated_files():
    return {"protocol.spec.json": json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n",
            "prompt_candidate.md": render_prompt()}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    out = Path(__file__).parent / "generated"
    if args.check:
        for name, text in generated_files().items():
            if (out / name).read_text(encoding="utf-8") != text:
                raise SystemExit("generated artifact drift: " + name)
        print("generated artifacts match specification")
    else:
        out.mkdir(exist_ok=True)
        for name, text in generated_files().items():
            path = out / name
            # Never overwrite a manually edited generated file without review.
            if path.exists() and path.read_text(encoding="utf-8") != text:
                raise SystemExit("existing generated artifact differs: " + name)
            if not path.exists():
                path.write_text(text, encoding="utf-8", newline="\n")
        print("generated candidate artifacts; not production-enabled")

if __name__ == "__main__":
    main()
