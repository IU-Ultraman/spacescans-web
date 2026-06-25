"""Tests for the idempotent ontology extension script."""
import json
from pathlib import Path


def _seed(base: Path):
    """Minimal generated-ontology fixture with the 3 parent nodes the
    extension targets. Social (000295) starts as a LEAF (no nodes file)."""
    (base / "nodes").mkdir(parents=True)
    (base / "metadata.json").write_text(json.dumps({
        "000093_2": {"id": "000093_2", "label": "Spatial_and_Contextual_Exposome", "definition": ""},
        "000292": {"id": "000292", "label": "Built_Environment_Exposome", "definition": ""},
        "000094_2": {"id": "000094_2", "label": "Natural_Environment_Exposome", "definition": ""},
        "000295": {"id": "000295", "label": "Social_Environment_Exposome", "definition": ""},
    }))
    (base / "search-index.json").write_text(json.dumps([
        {"id": "000295", "label": "Social_Environment_Exposome", "definition": ""},
    ]))
    (base / "index.json").write_text(json.dumps([]))
    # Exposome root's children: Built/Natural/Social — Social has_children False.
    (base / "nodes" / "000093_2.json").write_text(json.dumps([
        {"id": "000292", "label": "Built_Environment_Exposome", "definition": "", "has_children": True},
        {"id": "000094_2", "label": "Natural_Environment_Exposome", "definition": "", "has_children": True},
        {"id": "000295", "label": "Social_Environment_Exposome", "definition": "", "has_children": False},
    ]))
    (base / "nodes" / "000292.json").write_text(json.dumps([
        {"id": "000294", "label": "Food_Access_Exposome", "definition": "", "has_children": False},
    ]))
    (base / "nodes" / "000094_2.json").write_text(json.dumps([
        {"id": "000289", "label": "Noise", "definition": "", "has_children": False},
    ]))


def test_extend_adds_five_nodes_and_flips_social(tmp_path):
    from scripts.extend_ontology import extend_ontology, NEW_NODES, EXTENSION_MARKER

    _seed(tmp_path)
    extend_ontology(tmp_path)

    meta = json.loads((tmp_path / "metadata.json").read_text())
    search_ids = {it["id"] for it in json.loads((tmp_path / "search-index.json").read_text())}
    for node in NEW_NODES:
        assert node["id"] in meta, node["id"]
        assert meta[node["id"]]["definition"].endswith(EXTENSION_MARKER)
        assert node["id"] in search_ids

    # Social leaf became a parent file with its 2 children.
    social = json.loads((tmp_path / "nodes" / "000295.json").read_text())
    social_ids = {c["id"] for c in social}
    assert social_ids == {
        "SPACESCANS_Neighborhood_Deprivation_Index",
        "SPACESCANS_Community_Organization_Density",
    }
    # Built gained Walkability + Road_Proximity (kept Food_Access).
    built_ids = {c["id"] for c in json.loads((tmp_path / "nodes" / "000292.json").read_text())}
    assert {"SPACESCANS_Walkability", "SPACESCANS_Road_Proximity", "000294"} <= built_ids
    # Natural gained Bluespace (kept Noise).
    nat_ids = {c["id"] for c in json.loads((tmp_path / "nodes" / "000094_2.json").read_text())}
    assert {"SPACESCANS_Bluespace", "000289"} <= nat_ids
    # Social's has_children flipped True in the exposome root's child list.
    root = json.loads((tmp_path / "nodes" / "000093_2.json").read_text())
    social_entry = next(c for c in root if c["id"] == "000295")
    assert social_entry["has_children"] is True


def test_extend_is_idempotent(tmp_path):
    from scripts.extend_ontology import extend_ontology

    _seed(tmp_path)
    extend_ontology(tmp_path)
    first = {p.name: p.read_text() for p in (tmp_path / "nodes").glob("*.json")}
    first["metadata"] = (tmp_path / "metadata.json").read_text()
    first["search"] = (tmp_path / "search-index.json").read_text()

    extend_ontology(tmp_path)  # run again
    # No duplicate children anywhere.
    for f in (tmp_path / "nodes").glob("*.json"):
        ids = [c["id"] for c in json.loads(f.read_text())]
        assert len(ids) == len(set(ids)), f"dupes in {f.name}: {ids}"
    # Byte-identical to first run.
    assert (tmp_path / "metadata.json").read_text() == first["metadata"]
    assert (tmp_path / "search-index.json").read_text() == first["search"]


def test_child_lists_sorted_by_label(tmp_path):
    from scripts.extend_ontology import extend_ontology

    _seed(tmp_path)
    extend_ontology(tmp_path)
    for f in (tmp_path / "nodes").glob("*.json"):
        labels = [c["label"] for c in json.loads(f.read_text())]
        assert labels == sorted(labels), f"{f.name} not sorted: {labels}"
