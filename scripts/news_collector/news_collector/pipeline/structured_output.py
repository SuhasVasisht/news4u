"""Adapt Pydantic schemas to the review API's strict object contract."""
from copy import deepcopy


def review_schema(model):
    schema = deepcopy(model.model_json_schema())

    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            # URI is not a supported response format; Pydantic still validates URLs.
            if node.get("format") == "uri":
                node.pop("format")
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
