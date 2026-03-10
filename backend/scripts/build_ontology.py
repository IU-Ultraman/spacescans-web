"""Parse OWL file and output split JSON files for the frontend ontology browser."""
import json
import sys
from pathlib import Path
from collections import defaultdict


def _make_cls_id(cls):
    """Generate a unique ID from a class IRI, using the fragment or last path segment."""
    iri = cls.iri
    if "#" in iri:
        fragment = iri.rsplit("#", 1)[1]
    elif "/" in iri:
        fragment = iri.rsplit("/", 1)[1]
    else:
        fragment = cls.name
    return fragment


def build_ontology(owl_path: str, output_dir: str):
    from owlready2 import get_ontology

    output = Path(output_dir)
    nodes_dir = output / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    onto = get_ontology(f"file://{owl_path}").load()

    # Get skos namespace for definitions
    skos = onto.get_namespace("http://www.w3.org/2004/02/skos/core#")

    # Build parent -> children map
    children_map = defaultdict(list)
    class_info = {}
    # Map from owlready2 class object to our unique ID
    cls_to_id = {}

    # First pass: assign unique IDs (handle duplicate names from different namespaces)
    id_counts = defaultdict(int)
    all_classes = list(onto.classes())
    for cls in all_classes:
        base_id = _make_cls_id(cls)
        id_counts[base_id] += 1

    # Track how many times we've seen each base_id to disambiguate
    id_seen = defaultdict(int)
    for cls in all_classes:
        base_id = _make_cls_id(cls)
        if id_counts[base_id] > 1:
            id_seen[base_id] += 1
            cls_id = f"{base_id}_{id_seen[base_id]}"
        else:
            cls_id = base_id
        cls_to_id[cls] = cls_id

    # Second pass: collect class info and build hierarchy
    for cls in all_classes:
        cls_id = cls_to_id[cls]
        label = cls.label.first() if cls.label else cls.name

        # Get skos:definition if available
        definition = ""
        try:
            defn_list = skos.definition[cls]
            if defn_list:
                definition = str(defn_list[0])
        except Exception:
            pass

        # Fallback to rdfs:comment
        if not definition and hasattr(cls, "comment") and cls.comment:
            definition = str(cls.comment.first() or "")

        class_info[cls_id] = {
            "id": cls_id,
            "label": label,
            "definition": definition,
        }

        parents = cls.is_a
        is_root = True
        for parent in parents:
            if hasattr(parent, "name") and parent.name != "Thing" and parent in cls_to_id:
                parent_id = cls_to_id[parent]
                children_map[parent_id].append(cls_id)
                is_root = False

        if is_root:
            children_map["__root__"].append(cls_id)

    # Write index.json (top-level classes)
    roots = []
    for cls_id in children_map["__root__"]:
        info = dict(class_info.get(cls_id, {"id": cls_id, "label": cls_id, "definition": ""}))
        info["has_children"] = cls_id in children_map
        roots.append(info)
    roots.sort(key=lambda x: x["label"])
    (output / "index.json").write_text(json.dumps(roots, indent=2))

    # Write per-node files
    node_count = 0
    for parent_id, child_ids in children_map.items():
        if parent_id == "__root__":
            continue
        children = []
        for cls_id in child_ids:
            info = dict(class_info.get(cls_id, {"id": cls_id, "label": cls_id, "definition": ""}))
            info["has_children"] = cls_id in children_map
            children.append(info)
        children.sort(key=lambda x: x["label"])
        (nodes_dir / f"{parent_id}.json").write_text(json.dumps(children, indent=2))
        node_count += 1

    # Write metadata.json (all class details)
    (output / "metadata.json").write_text(json.dumps(class_info, indent=2))

    # Write search index (list of {id, label, definition} for client-side search)
    search_items = [
        {"id": v["id"], "label": v["label"], "definition": v["definition"]}
        for v in class_info.values()
    ]
    (output / "search-index.json").write_text(json.dumps(search_items, indent=2))

    print(f"Built ontology: {len(class_info)} classes, {node_count} parent nodes, {len(roots)} roots")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python build_ontology.py <owl_path> <output_dir>")
        sys.exit(1)
    build_ontology(sys.argv[1], sys.argv[2])
