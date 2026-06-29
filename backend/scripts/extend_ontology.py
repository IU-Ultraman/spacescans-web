"""Idempotently inject SPACESCANS-local extension nodes into the GENERATED
ontology JSON (frontend/public/ontology).

Two kinds of nodes are injected:
  1. NEW_NODES — 5 exposure concepts missing from the source SPACEO ontology
     (Walkability, NDI, Community_Organization_Density, Road_Proximity,
     Bluespace), attached under their environmental-domain parent.
  2. VALUE_COL_NODES — the per-variable outcome columns (value_cols) each
     variable produces in result.csv (e.g. cbp's r_religious, noise's
     l50dba_exi), attached as children of that variable's ontology node.

WHY this patches generated artifacts instead of the OWL source: the canonical
source `ontology files/SPACEO_20251203.owl` is not present in the repo, so we
cannot regenerate. The `SPACESCANS_` id prefix is the provenance marker.

IMPORTANT: if `build_ontology.py` is ever re-run from an OWL source, it will
OVERWRITE these nodes. You MUST re-run this script afterwards.
"""
import argparse
import json
from pathlib import Path

# Environmental-domain parents: 000292 Built, 000094_2 Natural, 000295 Social.
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

# Each variable's ontology node and the value_cols it produces. Definitions are
# baked from ExposomeVariablesList.xlsx (cbp/fara/ndi/walkability) and
# variable_metadata.json (noise/vnl/temis/nhd/tiger), per the 2026-06-29 spec.
_CBP = "SPACESCANS_Community_Organization_Density"
_FOOD = "000294"            # Food_Access_Exposome (fara_tract)
_NDI = "SPACESCANS_Neighborhood_Deprivation_Index"
_WALK = "SPACESCANS_Walkability"
_NOISE = "000289"           # Noise
_VNL = "000290"             # Light_at_Night
_UV = "000288"              # Ultraviolet_Radiation
_BLUE = "SPACESCANS_Bluespace"
_ROAD = "SPACESCANS_Road_Proximity"

# (col, parent, label, definition-without-the-column-suffix)
_VALUE_COLS = [
    # cbp_zcta5 — establishments per 10,000 population (ExposomeVariablesList CBP)
    ("r_religious", _CBP, "Religious organizations", "Number of establishments in religious organizations per 10,000 population."),
    ("r_civic", _CBP, "Civic & social associations", "Number of establishments in civic and social associations per 10,000 population."),
    ("r_business", _CBP, "Business associations", "Number of establishments in business associations per 10,000 population."),
    ("r_political", _CBP, "Political organizations", "Number of establishments in political organizations per 10,000 population."),
    ("r_professional", _CBP, "Professional organizations", "Number of establishments in professional organizations per 10,000 population."),
    ("r_labor", _CBP, "Labor organizations", "Number of establishments in labor organizations per 10,000 population."),
    ("r_bowling", _CBP, "Bowling centers", "Number of establishments in bowling centers per 10,000 population."),
    ("r_recreational", _CBP, "Fitness & recreational sports centers", "Number of establishments in fitness and recreational sports centers per 10,000 population."),
    ("r_golf", _CBP, "Golf courses & country clubs", "Number of establishments in golf courses and country clubs per 10,000 population."),
    ("r_sports", _CBP, "Sports teams & clubs", "Number of establishments in sports teams and clubs per 10,000 population."),
    # fara_tract — USDA FARA flags
    ("LILATracts_1And10", _FOOD, "Low-income & low-access tract (1/10 mi)", "Flag for low-income, low-access tracts at 1 mile (urban) / 10 miles (rural)."),
    ("LATracts1", _FOOD, "Low-access tract (1 mi)", "Flag for low-access tract at 1 mile."),
    ("HUNVFlag", _FOOD, "Low-vehicle-access tract", "Flag for a tract where >=100 households have no vehicle and are beyond half a mile from a supermarket."),
    ("LowIncomeTracts", _FOOD, "Low-income tract", "Flag for low-income tract."),
    # ndi
    ("ndi", _NDI, "NDI score", "Neighborhood Deprivation Index — composite socioeconomic deprivation score (z-score)."),
    # walkability
    ("NatWalkInd", _WALK, "National Walkability Index", "Relative walkability from the EPA National Walkability Index (1-20)."),
    # noise — BTS L50 dBA surfaces (imp/nat scenarios unverified)
    ("l50dba_exi", _NOISE, "Noise — existing conditions", "Existing-conditions daytime road+aviation transportation-noise surface, L50 dBA."),
    ("l50dba_imp", _NOISE, "Noise — alternative scenario (imp)", "Alternative-scenario daytime L50 transportation-noise surface (dBA); exact scenario pending verification against the BTS source."),
    ("l50dba_nat", _NOISE, "Noise — alternative scenario (nat)", "Alternative-scenario daytime L50 transportation-noise surface (dBA); exact scenario pending verification against the BTS source."),
    # vnl
    ("value", _VNL, "Night-time radiance", "Annual mean night-time light radiance (nanowatts/cm^2/sr) from the VIIRS Day/Night Band."),
    # temis — daily UV doses
    ("uvddc", _UV, "Daily DNA-damage UV dose", "Daily DNA-damage-weighted ultraviolet dose."),
    ("uvdec", _UV, "Daily erythemal UV dose", "Daily erythemally-weighted ultraviolet dose."),
    ("uvdvc", _UV, "Daily vitamin-D UV dose", "Daily vitamin-D-weighted ultraviolet dose."),
    ("uvief", _UV, "UV index at noon", "Ultraviolet index at local solar noon."),
    # nhd_bluespace — distances (m)
    ("dist_flow_m", _BLUE, "Distance to flowline", "Distance in meters to the nearest NHD flowline."),
    ("dist_water_m", _BLUE, "Distance to waterbody", "Distance in meters to the nearest NHD waterbody."),
    ("dist_area_m", _BLUE, "Distance to area feature", "Distance in meters to the nearest NHD area feature."),
    ("dist_coast_m", _BLUE, "Distance to coastline", "Distance in meters to the nearest coastline (99999 for inland addresses)."),
    ("dist_blue_m", _BLUE, "Distance to nearest blue feature", "Distance in meters to the nearest combined blue feature (flowline, waterbody, area, or coast)."),
    # tiger_proximity — distances (m)
    ("dist_pri", _ROAD, "Distance to primary road", "Distance in meters to the nearest TIGER/Line primary road (S1100)."),
    ("dist_sec", _ROAD, "Distance to secondary road", "Distance in meters to the nearest TIGER/Line secondary road (S1200)."),
    ("dist_prisec", _ROAD, "Distance to primary/secondary road", "Distance in meters to the nearest TIGER/Line primary or secondary road."),
]

VALUE_COL_NODES = [
    {"id": f"SPACESCANS_VC_{col}", "label": label, "parent": parent,
     "definition": f"{definition} (Result column: {col}.)"}
    for col, parent, label, definition in _VALUE_COLS
]

# has_children must read True for a node once it gains children. Pairs of
# (node_id, child-list file in which that node appears as an entry):
#  - 000295 (Social) appears under the exposome root and now has the 2 SPACESCANS
#    variable nodes as children.
#  - each of the 9 variable nodes appears under its domain file and now has
#    value_col children.
_HAS_CHILDREN_FLIPS = [
    ("000295", "000093_2.json"),
    ("000289", "000094_2.json"), ("000290", "000094_2.json"),
    ("000288", "000094_2.json"), ("SPACESCANS_Bluespace", "000094_2.json"),
    ("000294", "000292.json"), ("SPACESCANS_Walkability", "000292.json"),
    ("SPACESCANS_Road_Proximity", "000292.json"),
    ("SPACESCANS_Neighborhood_Deprivation_Index", "000295.json"),
    ("SPACESCANS_Community_Organization_Density", "000295.json"),
]


def _load(p: Path):
    return json.loads(p.read_text())


def _dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2))


def _inject(node, metadata, search, nodes_dir) -> bool:
    """Add/refresh one node in metadata + search-index + its parent child-list.
    Returns True if newly added to the parent list (False if it already existed)."""
    nid, label, parent = node["id"], node["label"], node["parent"]
    definition = node["definition"]

    metadata[nid] = {"id": nid, "label": label, "definition": definition}

    # Refresh-or-append in the search index so definition edits propagate on
    # re-run (append-only would keep a stale prior definition).
    entry = next((it for it in search if it["id"] == nid), None)
    if entry is None:
        search.append({"id": nid, "label": label, "definition": definition})
    else:
        entry.update({"label": label, "definition": definition})

    parent_file = nodes_dir / f"{parent}.json"
    children = _load(parent_file) if parent_file.exists() else []
    existing = next((c for c in children if c["id"] == nid), None)
    added = existing is None
    if existing is None:
        children.append({"id": nid, "label": label,
                         "definition": definition, "has_children": False})
    else:  # refresh in place (idempotency on label/definition tweaks)
        existing.update({"label": label, "definition": definition})
    children.sort(key=lambda x: x["label"])
    _dump(parent_file, children)
    return added


def extend_ontology(ontology_dir) -> dict:
    base = Path(ontology_dir)
    nodes_dir = base / "nodes"
    metadata = _load(base / "metadata.json")
    search = _load(base / "search-index.json")

    all_nodes = NEW_NODES + VALUE_COL_NODES
    added = sum(_inject(n, metadata, search, nodes_dir) for n in all_nodes)

    # Flip has_children True on every node that now has children.
    for node_id, in_file in _HAS_CHILDREN_FLIPS:
        container = nodes_dir / in_file
        if not container.exists():
            continue
        items = _load(container)
        for c in items:
            if c["id"] == node_id:
                c["has_children"] = True
        _dump(container, items)

    _dump(base / "metadata.json", metadata)
    _dump(base / "search-index.json", search)
    return {"added": added, "total": len(all_nodes),
            "new_nodes": len(NEW_NODES), "value_cols": len(VALUE_COL_NODES)}


if __name__ == "__main__":
    default_dir = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ontology"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology-dir", default=str(default_dir))
    args = parser.parse_args()
    result = extend_ontology(args.ontology_dir)
    print(f"extend_ontology: {result['added']} added / {result['total']} total "
          f"({result['new_nodes']} concept nodes + {result['value_cols']} value-col nodes) "
          f"-> {args.ontology_dir}")
