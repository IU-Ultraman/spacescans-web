"""Idempotently inject SPACESCANS-local extension nodes into the GENERATED
ontology JSON (frontend/public/ontology).

WHY this patches generated artifacts instead of the OWL source: the canonical
source `ontology files/SPACEO_20251203.owl` is not present in the repo, so we
cannot regenerate. These 5 concepts are missing from SPACEO and are added here
as clearly-marked local extensions, pending merge into the authoritative
ontology.

IMPORTANT: if `build_ontology.py` is ever re-run from an OWL source, it will
OVERWRITE these nodes. You MUST re-run this script afterwards.
"""
import argparse
import json
from pathlib import Path

EXTENSION_MARKER = " [SPACESCANS-local extension — pending merge into SPACEO]"

# parent ids: 000292 Built_Environment_Exposome, 000094_2 Natural_Environment_
# Exposome, 000295 Social_Environment_Exposome (currently a leaf).
NEW_NODES = [
    {"id": "SPACESCANS_Walkability", "label": "Walkability", "parent": "000292",
     "definition": "EPA National Walkability Index ranking neighborhoods on "
                   "walkability characteristics such as intersection density, "
                   "transit proximity, and employment mix."},
    {"id": "SPACESCANS_Neighborhood_Deprivation_Index",
     "label": "Neighborhood_Deprivation_Index", "parent": "000295",
     "definition": "Composite measure of neighborhood-level socioeconomic "
                   "deprivation derived from US Census ACS variables."},
    {"id": "SPACESCANS_Community_Organization_Density",
     "label": "Community_Organization_Density", "parent": "000295",
     "definition": "Per-capita density of community organization categories "
                   "(religious, civic, business, etc.) from US Census ZIP "
                   "Business Patterns."},
    {"id": "SPACESCANS_Road_Proximity", "label": "Road_Proximity", "parent": "000292",
     "definition": "Distance from a residence to the nearest TIGER/Line "
                   "primary, secondary, and combined primary+secondary roads."},
    {"id": "SPACESCANS_Bluespace", "label": "Bluespace", "parent": "000094_2",
     "definition": "Distance from a residence to the nearest NHD surface-water "
                   "feature (flowline, waterbody, area feature, coastline, and "
                   "combined blue feature)."},
]

# Parent whose has_children must flip True once it gains children, keyed by the
# child-list file in which that parent appears as an entry.
_LEAF_PARENT_TO_FLIP = ("000295", "000093_2.json")


def _load(p: Path):
    return json.loads(p.read_text())


def _dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2))


def extend_ontology(ontology_dir) -> dict:
    base = Path(ontology_dir)
    nodes_dir = base / "nodes"
    metadata = _load(base / "metadata.json")
    search = _load(base / "search-index.json")
    search_ids = {it["id"] for it in search}

    added = 0
    for node in NEW_NODES:
        nid, label, parent = node["id"], node["label"], node["parent"]
        definition = node["definition"] + EXTENSION_MARKER

        metadata[nid] = {"id": nid, "label": label, "definition": definition}

        if nid not in search_ids:
            search.append({"id": nid, "label": label, "definition": definition})
            search_ids.add(nid)

        parent_file = nodes_dir / f"{parent}.json"
        children = _load(parent_file) if parent_file.exists() else []
        existing = next((c for c in children if c["id"] == nid), None)
        if existing is None:
            children.append({"id": nid, "label": label,
                             "definition": definition, "has_children": False})
            added += 1
        else:  # refresh in place (keeps idempotency on label/definition tweaks)
            existing.update({"label": label, "definition": definition,
                             "has_children": False})
        children.sort(key=lambda x: x["label"])
        _dump(parent_file, children)

    # Flip has_children on the former-leaf parent where it appears as a child.
    leaf_id, in_file = _LEAF_PARENT_TO_FLIP
    container = nodes_dir / in_file
    if container.exists():
        items = _load(container)
        for c in items:
            if c["id"] == leaf_id:
                c["has_children"] = True
        _dump(container, items)

    _dump(base / "metadata.json", metadata)
    _dump(base / "search-index.json", search)
    return {"added": added, "total": len(NEW_NODES)}


if __name__ == "__main__":
    default_dir = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ontology"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology-dir", default=str(default_dir))
    args = parser.parse_args()
    result = extend_ontology(args.ontology_dir)
    print(f"extend_ontology: {result['added']} added / {result['total']} total "
          f"-> {args.ontology_dir}")
