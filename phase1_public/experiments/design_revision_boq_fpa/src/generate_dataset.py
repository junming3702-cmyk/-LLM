"""Generate the fixed 24-case synthetic dataset for the pilot.

The generator is deliberately standard-library-only and has no network, LLM,
BIM, or external-file dependency.  Its output is canonical JSONL so that a
fresh generation can be compared byte-for-byte with the recorded input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _candidate(
    *,
    candidate_id: str,
    description: str,
    drawing_id: str,
    revised_version: str,
    work_item: str,
    source_version: str,
    locator: str,
    quantity: float,
    unit: str,
    unit_rate: float,
    tokens: list[str],
    support_evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "description": description,
        "drawing_id": drawing_id,
        "revised_version": revised_version,
        "work_item": work_item,
        "source_version": source_version,
        "locator": locator,
        "quantity": quantity,
        "unit": unit,
        "unit_rate": unit_rate,
        "tokens": tokens,
        "support_evidence_ids": support_evidence_ids,
    }


def _support(
    *,
    evidence_id: str,
    candidate_id: str,
    source_version: str,
    locator: str,
    text: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "kind": "support",
        "candidate_id": candidate_id,
        "source_version": source_version,
        "locator": locator,
        "text": text,
    }


def _conflict(
    *,
    evidence_id: str,
    candidate_id: str,
    source_version: str,
    locator: str,
    text: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "kind": "conflict",
        "candidate_id": candidate_id,
        "source_version": source_version,
        "locator": locator,
        "text": text,
    }


def _base_row(
    *,
    case_id: str,
    case_type: str,
    drawing_id: str,
    baseline_version: str,
    revised_version: str,
    description: str,
    tokens: list[str],
    zone: str,
    work_item: str,
    quantity: float,
    unit_rate: float,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_type": case_type,
        "design_revision": {
            "drawing_id": drawing_id,
            "baseline_version": baseline_version,
            "revised_version": revised_version,
            "description": description,
            "change_tokens": tokens,
            "marked_locator": (
                f"drawings/{drawing_id}_rev{revised_version}.pdf#mark-01"
            ),
            "zone": zone,
        },
        "target_work_item": work_item,
        "target_quantity": quantity,
        "target_unit_rate": unit_rate,
    }


def _explicit(
    *,
    case_id: str,
    drawing_id: str,
    description: str,
    tokens: list[str],
    zone: str,
    work_item: str,
    quantity: float,
    unit_rate: float,
) -> dict[str, Any]:
    revised = "B"
    good_id = f"BQ-EXP-{case_id[-2:]}"
    support_1 = f"{case_id}-S1"
    support_2 = f"{case_id}-S2"
    case = _base_row(
        case_id=case_id,
        case_type="explicit_mapping",
        drawing_id=drawing_id,
        baseline_version="A",
        revised_version=revised,
        description=description,
        tokens=tokens,
        zone=zone,
        work_item=work_item,
        quantity=quantity,
        unit_rate=unit_rate,
    )
    good = _candidate(
        candidate_id=good_id,
        description=f"Additional {description.lower()} work",
        drawing_id=drawing_id,
        revised_version=revised,
        work_item=work_item,
        source_version="BoQ-Rev03",
        locator=f"boq/BoQ-Rev03.xlsx#sheet=BoQ&cell={work_item}",
        quantity=quantity,
        unit="m",
        unit_rate=unit_rate,
        tokens=tokens + ["additional", "work"],
        support_evidence_ids=[support_1, support_2],
    )
    alternative = _candidate(
        candidate_id=f"BQ-ALT-{case_id[-2:]}",
        description="Unrelated finishing work alternative",
        drawing_id=f"{drawing_id}-ALT",
        revised_version="A",
        work_item=f"ALT-{work_item}",
        source_version="BoQ-Rev03",
        locator=f"boq/BoQ-Rev03.xlsx#sheet=BoQ&cell=ALT-{work_item}",
        quantity=quantity,
        unit="m2",
        unit_rate=unit_rate / 2,
        tokens=["unrelated", "finishing", "alternative"],
        support_evidence_ids=[],
    )
    case["candidates"] = [good, alternative]
    case["support_evidence"] = [
        _support(
            evidence_id=support_1,
            candidate_id=good_id,
            source_version=f"Drawing-{drawing_id}-Rev{revised}",
            locator=f"drawings/{drawing_id}_rev{revised}.pdf#mark-01",
            text=f"Marked revision identifies the {zone} change described in the case.",
        ),
        _support(
            evidence_id=support_2,
            candidate_id=good_id,
            source_version="Instruction-2026-01",
            locator=f"instructions/{case_id}_instruction.pdf#page=1",
            text=f"Written instruction confirms {work_item} as the affected work item.",
        ),
    ]
    case["conflict_evidence"] = []
    case["gold"] = {
        "status": "accept",
        "candidate_id": good_id,
        "rationale": "Unique supported mapping with matching drawing revision and no conflict.",
    }
    return case


def _ambiguous(
    *,
    case_id: str,
    drawing_id: str,
    description: str,
    tokens: list[str],
    zone: str,
    work_item: str,
    quantity: float,
    unit_rate: float,
) -> dict[str, Any]:
    revised = "C"
    first_id = f"BQ-AMB-{case_id[-2:]}A"
    second_id = f"BQ-AMB-{case_id[-2:]}B"
    support_1 = f"{case_id}-S1"
    support_2 = f"{case_id}-S2"
    case = _base_row(
        case_id=case_id,
        case_type="ambiguous_alternatives",
        drawing_id=drawing_id,
        baseline_version="B",
        revised_version=revised,
        description=description,
        tokens=tokens,
        zone=zone,
        work_item=work_item,
        quantity=quantity,
        unit_rate=unit_rate,
    )
    shared_tokens = tokens + ["revised", "area"]
    case["candidates"] = [
        _candidate(
            candidate_id=first_id,
            description=f"Alternative A: {description.lower()}",
            drawing_id=drawing_id,
            revised_version=revised,
            work_item=f"{work_item}-A",
            source_version="BoQ-Rev04",
            locator=f"boq/BoQ-Rev04.xlsx#sheet=BoQ&cell={work_item}-A",
            quantity=quantity,
            unit="m",
            unit_rate=unit_rate,
            tokens=shared_tokens,
            support_evidence_ids=[support_1],
        ),
        _candidate(
            candidate_id=second_id,
            description=f"Alternative B: {description.lower()}",
            drawing_id=drawing_id,
            revised_version=revised,
            work_item=f"{work_item}-B",
            source_version="BoQ-Rev04",
            locator=f"boq/BoQ-Rev04.xlsx#sheet=BoQ&cell={work_item}-B",
            quantity=quantity + 1,
            unit="m",
            unit_rate=unit_rate,
            tokens=shared_tokens,
            support_evidence_ids=[support_2],
        ),
    ]
    case["support_evidence"] = [
        _support(
            evidence_id=support_1,
            candidate_id=first_id,
            source_version=f"Drawing-{drawing_id}-Rev{revised}",
            locator=f"drawings/{drawing_id}_rev{revised}.pdf#mark-A",
            text="The markup supports the location but does not disambiguate the two BoQ alternatives.",
        ),
        _support(
            evidence_id=support_2,
            candidate_id=second_id,
            source_version=f"Quotation-{case_id}",
            locator=f"quotations/{case_id}.pdf#page=2",
            text="The quotation supports the same description but does not disambiguate the two BoQ alternatives.",
        ),
    ]
    case["conflict_evidence"] = []
    case["gold"] = {
        "status": "abstain",
        "candidate_id": None,
        "rationale": "Two equally supported alternatives remain unresolved by the available evidence.",
    }
    return case


def _conflicting(
    *,
    case_id: str,
    drawing_id: str,
    description: str,
    tokens: list[str],
    zone: str,
    work_item: str,
    quantity: float,
    unit_rate: float,
) -> dict[str, Any]:
    revised = "D"
    candidate_id = f"BQ-CON-{case_id[-2:]}"
    support_id = f"{case_id}-S1"
    conflict_id = f"{case_id}-X1"
    case = _base_row(
        case_id=case_id,
        case_type="cross_document_version_conflict",
        drawing_id=drawing_id,
        baseline_version="C",
        revised_version=revised,
        description=description,
        tokens=tokens,
        zone=zone,
        work_item=work_item,
        quantity=quantity,
        unit_rate=unit_rate,
    )
    case["candidates"] = [
        _candidate(
            candidate_id=candidate_id,
            description=f"{description} under drawing revision {revised}",
            drawing_id=drawing_id,
            revised_version=revised,
            work_item=work_item,
            source_version="BoQ-Rev05",
            locator=f"boq/BoQ-Rev05.xlsx#sheet=BoQ&cell={work_item}",
            quantity=quantity,
            unit="m",
            unit_rate=unit_rate,
            tokens=tokens + ["revision", revised.lower()],
            support_evidence_ids=[support_id],
        )
    ]
    case["support_evidence"] = [
        _support(
            evidence_id=support_id,
            candidate_id=candidate_id,
            source_version=f"Drawing-{drawing_id}-Rev{revised}",
            locator=f"drawings/{drawing_id}_rev{revised}.pdf#mark-01",
            text="The marked drawing supports the candidate mapping.",
        )
    ]
    case["conflict_evidence"] = [
        _conflict(
            evidence_id=conflict_id,
            candidate_id=candidate_id,
            source_version=f"Instruction-{case_id}-RevC",
            locator=f"instructions/{case_id}_revC.pdf#page=1",
            text="An earlier instruction records a different revision and scope; the version conflict must be reviewed.",
        )
    ]
    case["gold"] = {
        "status": "abstain",
        "candidate_id": None,
        "rationale": "Cross-document/version conflict prevents an unqualified attribution.",
    }
    return case


def _insufficient(
    *,
    case_id: str,
    drawing_id: str,
    description: str,
    tokens: list[str],
    zone: str,
    work_item: str,
    quantity: float,
    unit_rate: float,
) -> dict[str, Any]:
    revised = "E"
    candidate_id = f"BQ-INS-{case_id[-2:]}"
    case = _base_row(
        case_id=case_id,
        case_type="insufficient_evidence",
        drawing_id=drawing_id,
        baseline_version="D",
        revised_version=revised,
        description=description,
        tokens=tokens,
        zone=zone,
        work_item=work_item,
        quantity=quantity,
        unit_rate=unit_rate,
    )
    case["candidates"] = [
        _candidate(
            candidate_id=candidate_id,
            description=f"Partial candidate for {description.lower()}",
            drawing_id=drawing_id,
            revised_version=revised,
            work_item=work_item,
            source_version="BoQ-Rev06",
            locator=f"boq/BoQ-Rev06.xlsx#sheet=BoQ&cell={work_item}",
            quantity=quantity,
            unit="m",
            unit_rate=unit_rate,
            tokens=tokens[:4],
            support_evidence_ids=[],
        )
    ]
    case["support_evidence"] = []
    case["conflict_evidence"] = []
    case["gold"] = {
        "status": "abstain",
        "candidate_id": None,
        "rationale": "The candidate lacks a supporting source attribution in the case record.",
    }
    return case


def build_cases() -> list[dict[str, Any]]:
    explicit_rows = [
        ("EXP-01", "DR-A101", "North fire-rated partition length increase", ["north", "fire", "rated", "partition", "length", "increase"], "north", "C12", 12.0, 840.0),
        ("EXP-02", "DR-A202", "East acoustic door opening addition", ["east", "acoustic", "door", "opening", "addition", "frame"], "east", "D08", 4.0, 2600.0),
        ("EXP-03", "DR-A303", "Plantroom cable tray route extension", ["plantroom", "cable", "tray", "route", "extension", "service"], "plantroom", "E21", 18.0, 510.0),
        ("EXP-04", "DR-A404", "Roof drainage outlet relocation", ["roof", "drainage", "outlet", "relocation", "rainwater", "pipe"], "roof", "F05", 6.0, 1180.0),
        ("EXP-05", "DR-A505", "Lobby stone skirting height change", ["lobby", "stone", "skirting", "height", "change", "finish"], "lobby", "G14", 22.0, 390.0),
        ("EXP-06", "DR-A606", "Basement fire shutter width revision", ["basement", "fire", "shutter", "width", "revision", "opening"], "basement", "H03", 3.0, 9200.0),
    ]
    ambiguous_rows = [
        ("AMB-01", "DR-B101", "North ceiling grid alteration", ["north", "ceiling", "grid", "alteration", "module", "layout"], "north", "J11", 16.0, 280.0),
        ("AMB-02", "DR-B202", "East partition finish substitution", ["east", "partition", "finish", "substitution", "surface", "material"], "east", "K07", 30.0, 460.0),
        ("AMB-03", "DR-B303", "Plantroom valve access change", ["plantroom", "valve", "access", "change", "panel", "service"], "plantroom", "L19", 5.0, 1450.0),
        ("AMB-04", "DR-B404", "Roof insulation build-up revision", ["roof", "insulation", "build", "up", "revision", "layer"], "roof", "M04", 42.0, 320.0),
        ("AMB-05", "DR-B505", "Lobby signage support adjustment", ["lobby", "signage", "support", "adjustment", "bracket", "location"], "lobby", "N16", 8.0, 750.0),
        ("AMB-06", "DR-B606", "Basement sump pump arrangement change", ["basement", "sump", "pump", "arrangement", "change", "duty"], "basement", "P02", 2.0, 6800.0),
    ]
    conflict_rows = [
        ("CON-01", "DR-C101", "North smoke damper scope revision", ["north", "smoke", "damper", "scope", "revision", "duct"], "north", "Q10", 7.0, 1320.0),
        ("CON-02", "DR-C202", "East glazing panel replacement", ["east", "glazing", "panel", "replacement", "window", "frame"], "east", "R06", 9.0, 2100.0),
        ("CON-03", "DR-C303", "Plantroom pump base modification", ["plantroom", "pump", "base", "modification", "plinth", "equipment"], "plantroom", "S18", 3.0, 3850.0),
        ("CON-04", "DR-C404", "Roof access ladder extension", ["roof", "access", "ladder", "extension", "steel", "height"], "roof", "T03", 5.0, 1950.0),
        ("CON-05", "DR-C505", "Lobby balustrade height alteration", ["lobby", "balustrade", "height", "alteration", "guard", "rail"], "lobby", "U13", 14.0, 990.0),
        ("CON-06", "DR-C606", "Basement waterproofing detail change", ["basement", "waterproofing", "detail", "change", "membrane", "joint"], "basement", "V01", 25.0, 510.0),
    ]
    insufficient_rows = [
        ("INS-01", "DR-D101", "North façade louvre adjustment", ["north", "facade", "louvre", "adjustment", "screen", "opening"], "north", "W09", 11.0, 780.0),
        ("INS-02", "DR-D202", "East sanitary pipe rerouting", ["east", "sanitary", "pipe", "rerouting", "drain", "service"], "east", "X05", 21.0, 430.0),
        ("INS-03", "DR-D303", "Plantroom control panel relocation", ["plantroom", "control", "panel", "relocation", "electrical", "cabinet"], "plantroom", "Y17", 2.0, 2850.0),
        ("INS-04", "DR-D404", "Roof parapet capping alteration", ["roof", "parapet", "capping", "alteration", "edge", "metal"], "roof", "Z02", 19.0, 610.0),
        ("INS-05", "DR-D505", "Lobby access control reader change", ["lobby", "access", "control", "reader", "change", "security"], "lobby", "AA12", 4.0, 1680.0),
        ("INS-06", "DR-D606", "Basement ventilation grille revision", ["basement", "ventilation", "grille", "revision", "opening", "air"], "basement", "AB08", 10.0, 520.0),
    ]
    cases: list[dict[str, Any]] = []
    for row in explicit_rows:
        cases.append(_explicit(case_id=row[0], drawing_id=row[1], description=row[2], tokens=row[3], zone=row[4], work_item=row[5], quantity=row[6], unit_rate=row[7]))
    for row in ambiguous_rows:
        cases.append(_ambiguous(case_id=row[0], drawing_id=row[1], description=row[2], tokens=row[3], zone=row[4], work_item=row[5], quantity=row[6], unit_rate=row[7]))
    for row in conflict_rows:
        cases.append(_conflicting(case_id=row[0], drawing_id=row[1], description=row[2], tokens=row[3], zone=row[4], work_item=row[5], quantity=row[6], unit_rate=row[7]))
    for row in insufficient_rows:
        cases.append(_insufficient(case_id=row[0], drawing_id=row[1], description=row[2], tokens=row[3], zone=row[4], work_item=row[5], quantity=row[6], unit_rate=row[7]))
    return cases


def write_jsonl(cases: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = build_cases()
    if len(cases) != 24:
        raise RuntimeError(f"expected 24 cases, generated {len(cases)}")
    write_jsonl(cases, args.output)
    print(f"generated_cases={len(cases)}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
