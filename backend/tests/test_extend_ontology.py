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
        {"id": "000294", "label": "FARA_Exposome", "definition": "", "has_children": False},
    ]))
    # Natural's existing SPACEO leaves that gain value_col children.
    (base / "nodes" / "000094_2.json").write_text(json.dumps([
        {"id": "000289", "label": "Noise", "definition": "", "has_children": False},
        {"id": "000290", "label": "Light_at_Night", "definition": "", "has_children": False},
        {"id": "000288", "label": "Ultraviolet_Radiation", "definition": "", "has_children": False},
    ]))


def test_extend_adds_five_nodes_and_flips_social(tmp_path):
    from scripts.extend_ontology import extend_ontology, NEW_NODES

    _seed(tmp_path)
    extend_ontology(tmp_path)

    meta = json.loads((tmp_path / "metadata.json").read_text())
    search_ids = {it["id"] for it in json.loads((tmp_path / "search-index.json").read_text())}
    for node in NEW_NODES:
        assert node["id"] in meta, node["id"]
        # Definition is the plain text — no user-facing extension marker.
        assert meta[node["id"]]["definition"] == node["definition"]
        assert "SPACESCANS-local extension" not in meta[node["id"]]["definition"]
        assert node["id"] in search_ids

    # Social leaf became a parent file with its 2 children.
    social = json.loads((tmp_path / "nodes" / "000295.json").read_text())
    social_ids = {c["id"] for c in social}
    assert social_ids == {
        "SPACESCANS_Neighborhood_Deprivation_Index",
        "SPACESCANS_Community_Organization_Density",
    }
    # Built gained Walkability + Road_Proximity (kept FARA).
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


def test_value_col_nodes_attached_under_variable_nodes(tmp_path):
    from scripts.extend_ontology import extend_ontology, VALUE_COL_NODES

    _seed(tmp_path)
    extend_ontology(tmp_path)

    meta = json.loads((tmp_path / "metadata.json").read_text())
    search_ids = {it["id"] for it in json.loads((tmp_path / "search-index.json").read_text())}

    # All ~32 value_col nodes land in metadata + search, with a "Result column:"
    # provenance suffix.
    assert len(VALUE_COL_NODES) == 58  # 32 original + 24 acag + 2 faqsd
    for n in VALUE_COL_NODES:
        assert n["id"] in meta, n["id"]
        assert n["id"] in search_ids, n["id"]
        assert "(Result column:" in meta[n["id"]]["definition"]

    # Spot-check placement: cbp outcome under Community_Organization_Density,
    # noise outcome under Noise (000289).
    cbp_children = {c["id"] for c in json.loads(
        (tmp_path / "nodes" / "SPACESCANS_Community_Organization_Density.json").read_text())}
    assert "SPACESCANS_VC_r_religious" in cbp_children
    assert len(cbp_children) == 10
    noise_children = {c["id"] for c in json.loads(
        (tmp_path / "nodes" / "000289.json").read_text())}
    assert {"SPACESCANS_VC_l50dba_exi", "SPACESCANS_VC_l50dba_imp",
            "SPACESCANS_VC_l50dba_nat"} == noise_children

    # Every variable node now reads has_children == True in its domain file.
    natural = {c["id"]: c for c in json.loads((tmp_path / "nodes" / "000094_2.json").read_text())}
    for vid in ("000289", "000290", "000288", "SPACESCANS_Bluespace"):
        assert natural[vid]["has_children"] is True, vid
    built = {c["id"]: c for c in json.loads((tmp_path / "nodes" / "000292.json").read_text())}
    for vid in ("000294", "SPACESCANS_Walkability", "SPACESCANS_Road_Proximity"):
        assert built[vid]["has_children"] is True, vid
    social = {c["id"]: c for c in json.loads((tmp_path / "nodes" / "000295.json").read_text())}
    for vid in ("SPACESCANS_Neighborhood_Deprivation_Index",
                "SPACESCANS_Community_Organization_Density"):
        assert social[vid]["has_children"] is True, vid


def test_parents_index_covers_every_child(tmp_path):
    """The wizard opens branches by walking child -> parent, so the index has
    to be written AFTER the injections (the value_col nodes are children too)
    and has to carry the deep air-quality chain, which is what made the two
    air exposures look absent while nine others showed."""
    from scripts.extend_ontology import extend_ontology

    _seed(tmp_path)
    extend_ontology(tmp_path)

    parents = json.loads((tmp_path / "parents.json").read_text())
    # Plain hierarchy edges.
    assert parents["000294"] == ["000292"]
    assert parents["000292"] == ["000093_2"]
    # Nodes injected by this run are in the index (not a stale pre-injection scan).
    assert parents["SPACESCANS_Neighborhood_Deprivation_Index"] == ["000295"]
    # Value-col children point at their variable node.
    value_cols = json.loads((tmp_path / "nodes" / "000289.json").read_text())
    assert value_cols, "Noise should have gained value_col children"
    assert parents[value_cols[0]["id"]] == ["000289"]
    # Every id that appears as someone's child is in the index, and no node is
    # its own parent.
    for f in (tmp_path / "nodes").glob("*.json"):
        for child in json.loads(f.read_text()):
            assert f.stem in parents[child["id"]], (child["id"], f.stem)
            assert child["id"] != f.stem


def test_parents_index_records_multiple_parents(tmp_path):
    """A few ontology nodes hang under two parents; the wizard expands both."""
    from scripts.extend_ontology import write_parents_index

    (tmp_path / "nodes").mkdir(parents=True)
    (tmp_path / "nodes" / "A.json").write_text(json.dumps(
        [{"id": "shared", "label": "s", "definition": "", "has_children": False}]))
    (tmp_path / "nodes" / "B.json").write_text(json.dumps(
        [{"id": "shared", "label": "s", "definition": "", "has_children": False}]))

    assert write_parents_index(tmp_path) == 1
    assert json.loads((tmp_path / "parents.json").read_text())["shared"] == ["A", "B"]
