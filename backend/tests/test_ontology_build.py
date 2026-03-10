import tempfile
from pathlib import Path

import os

# Allow override via environment variable; fall back to relative path from repo root
_default_owl = Path(__file__).resolve().parent.parent.parent / "ontology files" / "SPACEO_20251203.owl"
OWL_PATH = Path(os.environ.get("OWL_PATH", str(_default_owl)))


def test_build_ontology_outputs():
    if not OWL_PATH.exists():
        import pytest
        pytest.skip("OWL file not found")
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        from scripts.build_ontology import build_ontology
        build_ontology(str(OWL_PATH), str(output_dir))
        assert (output_dir / "index.json").exists()
        assert (output_dir / "nodes").is_dir()
        import json
        index = json.loads((output_dir / "index.json").read_text())
        assert isinstance(index, list)
        assert len(index) > 0
        # Each root should have a name and id
        for item in index:
            assert "id" in item
            assert "label" in item
            assert "has_children" in item
        # Check at least one node file exists
        node_files = list((output_dir / "nodes").glob("*.json"))
        assert len(node_files) > 0
        # Check search index and metadata were generated
        assert (output_dir / "search-index.json").exists()
        assert (output_dir / "metadata.json").exists()
        search = json.loads((output_dir / "search-index.json").read_text())
        assert isinstance(search, list)
        assert len(search) > 0
        # Each search item should have id, label, definition
        for item in search:
            assert "id" in item
            assert "label" in item
            assert "definition" in item
        # Metadata should be a dict keyed by class id
        metadata = json.loads((output_dir / "metadata.json").read_text())
        assert isinstance(metadata, dict)
        assert len(metadata) > 0
        for key, val in list(metadata.items())[:5]:
            assert "id" in val
            assert "label" in val
            assert "definition" in val
