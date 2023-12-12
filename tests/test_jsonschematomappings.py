import json
import os
import sys
from unittest.mock import mock_open, patch

import fastjsonschema
import pytest
from deepdiff import DeepDiff

from jsonschematomappings import (
    JSONSchemaToMappings,
    SchemaParsingException,
    jsonschematomappings,
    main,
    process_arguments,
)

from .conftest import RESOURCES_DIR, ObjectView


def test_process_arguments_valid():
    sys.argv = [
        "jsonschematomappings.py",
        "foo.json",
    ]
    args = process_arguments()
    assert args.json_schema == ["foo.json"]


def test_process_arguments_missing_required():
    sys.argv = [
        "jsonschematomappings.py",
    ]
    with pytest.raises(SystemExit):
        process_arguments()


def test_process_arguments_multiple():
    sys.argv = [
        "jsonschematomappings.py",
        "foo.json",
        "bar.json",
    ]
    with pytest.raises(SystemExit):
        process_arguments()


@patch(
    "jsonschematomappings.process_arguments",
    return_value=ObjectView({"json_schema": ["foo.json"], "template": None}),
)
@patch(
    "jsonschematomappings.jsonschematomappings",
    return_value={"foo": "bar"},
)
def test_main(mock_jsonschematomappings, mock_process_arguments, capsys):
    main()

    mock_process_arguments.assert_called_once()
    mock_jsonschematomappings.assert_called_once_with("foo.json", None)

    captured = capsys.readouterr()
    assert captured.out == '{\n  "foo": "bar"\n}\n'


@patch.object(JSONSchemaToMappings, "__init__", return_value=None)
@patch.object(JSONSchemaToMappings, "to_mappings", return_value={"foo": "bar"})
def test_jsonschematomappings(mock_to_mappings, mock_init):
    assert jsonschematomappings("foo.json") == {"foo": "bar"}
    mock_init.assert_called_once_with("foo.json", None)
    mock_to_mappings.assert_called_once()


def test_jsonschematomappings_template():
    assert jsonschematomappings(
        json_schema={"properties": {"name": {"type": "string"}}},
        template={"mappings": {"foo": "bar"}, "settings": {"some": "setting"}},
    ) == {
        "mappings": {"foo": "bar", "properties": {"name": {"type": "keyword"}}},
        "settings": {"some": "setting"},
    }


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data='{"mappings": {"foo": "bar"}, "settings": {"some": "setting"}}',
)
def test_jsonschematomappings_template_file(mock_open):
    assert jsonschematomappings(
        json_schema={"properties": {"name": {"type": "string"}}},
        template="fake_template.json",
    ) == {
        "mappings": {"foo": "bar", "properties": {"name": {"type": "keyword"}}},
        "settings": {"some": "setting"},
    }


def test_jsonschematomappings_regression():
    mappings = jsonschematomappings(
        os.path.join(RESOURCES_DIR, "test_json_schema.json")
    )
    with open(os.path.join(RESOURCES_DIR, "test_json_schema_mappings.json"), "rt") as f:
        expected = json.load(f)

    assert DeepDiff(mappings, expected) == {}


@patch.object(JSONSchemaToMappings, "_load_and_validate", return_value={"foo": "bar"})
def test_init(mock_load_and_validate):
    mapper = JSONSchemaToMappings("foo.json")

    assert mapper.json_schema == {"foo": "bar"}
    mock_load_and_validate.assert_called_once_with("foo.json")


def test_init_json_schema_file_missing():
    with pytest.raises(FileNotFoundError):
        JSONSchemaToMappings("does_not_exist.json")


def test_init_template_file_missing():
    with pytest.raises(FileNotFoundError):
        JSONSchemaToMappings({"properties": {}}, "does_not_exist.json")


@patch.object(JSONSchemaToMappings, "_convert_property", return_value={"foo": "bar"})
def test_to_mappings(mock_convert_property):
    assert JSONSchemaToMappings({"properties": {}}).to_mappings() == {
        "mappings": {"properties": {"foo": "bar"}}
    }


@patch.object(JSONSchemaToMappings, "_validate_json_schema")
@patch.object(JSONSchemaToMappings, "_load_json_doc")
def test__load_and_validate_dict(mock_load, mock_validate):
    JSONSchemaToMappings({"foo": "bar"})
    mock_load.assert_not_called()
    mock_validate.assert_called_once_with({"foo": "bar"})


@patch.object(JSONSchemaToMappings, "_validate_json_schema")
@patch.object(JSONSchemaToMappings, "_load_json_doc", return_value={"foo": "bar"})
def test__load_and_validate_file(mock_load, mock_validate):
    JSONSchemaToMappings("foo.json")
    mock_load.assert_called_once_with("foo.json")
    mock_validate.assert_called_once_with({"foo": "bar"})


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data='{"foo": "bar"}',
)
@patch.object(JSONSchemaToMappings, "_validate_json_schema")
def test__load_json_doc(mock_validate, mock_open):
    mapper = JSONSchemaToMappings("foo.json")
    assert mapper.json_schema == {"foo": "bar"}


def test__validate_schema_valid():
    mapper = JSONSchemaToMappings({"properties": {}})
    assert mapper.json_schema == {"properties": {}}


def test__validate_schema_invalid():
    with pytest.raises(fastjsonschema.JsonSchemaException):
        JSONSchemaToMappings(
            {"properties": {}, "required": "this should be an array not a string"}
        )


def test__validate_schema_missing_properties():
    with pytest.raises(KeyError):
        JSONSchemaToMappings({})


def test__defs():
    assert JSONSchemaToMappings({"properties": {}, "$defs": "foo"})._defs == "foo"


def test__defs_missing():
    assert JSONSchemaToMappings({"properties": {}})._defs == {}


def test__def_replace_key():
    assert (
        JSONSchemaToMappings({"properties": {}, "$id": "foo"})._def_replace_key
        == "foo#/$defs/"
    )


def test__def_replace_key_no_id():
    assert JSONSchemaToMappings({"properties": {}})._def_replace_key == "#/$defs/"


def test__expand_def():
    defs = {"foo": {"bar": "foo"}}
    mapper = JSONSchemaToMappings({"properties": {}, "$defs": defs})
    assert mapper._expand_def({"$ref": "#/$defs/foo"}) == {"bar": "foo"}


def test__expand_def_missing_def():
    mapper = JSONSchemaToMappings({"properties": {}})
    with pytest.raises(SchemaParsingException) as e:
        mapper._expand_def({"$ref": "#/$defs/foo"})
    assert "Unable to find definition for reference 'foo'" in str(e)


@pytest.mark.parametrize(
    ("d", "u", "r"),
    (
        ({}, {"foo": "bar"}, {"foo": "bar"}),
        ({"foo": "bar"}, {}, {"foo": "bar"}),
        ({"foo": "bar"}, {"boo": "far"}, {"foo": "bar", "boo": "far"}),
        ({"foo": "bar"}, {"foo": "far"}, {"foo": "far"}),
        (
            {"foo": {"one": "car", "two": "bar"}},
            {"foo": {"two": "tar"}},
            {"foo": {"one": "car", "two": "tar"}},
        ),
    ),
)
def test__update_dict(d, u, r):
    mapper = JSONSchemaToMappings({"properties": {}})
    assert mapper._update_dict(d, u) == r


@pytest.mark.parametrize(
    ("schema", "mappings"),
    (
        (
            {"name": {"description": "some text", "type": "string"}},
            {"name": {"type": "keyword"}},
        ),
        (
            {"name": {"type": "integer"}},
            {"name": {"type": "long"}},
        ),
        (
            {"name": {"type": "boolean"}},
            {"name": {"type": "boolean"}},
        ),
        (
            {"name": {"type": "float"}},
            {"name": {"type": "float"}},
        ),
        (
            {"name": {"type": "number"}},
            {"name": {"type": "float"}},
        ),
        (
            {"name": {"$ref": "foo"}},
            {"name": {"type": "long"}},
        ),
        (
            {"name": {"type": "string"}, "age": {"type": "integer"}},
            {"name": {"type": "keyword"}, "age": {"type": "long"}},
        ),
        (
            {"name": {"type": "object", "properties": {"subprop": {"type": "string"}}}},
            {"name": {"properties": {"subprop": {"type": "keyword"}}}},
        ),
        (
            {"name": {"type": "object"}},
            {"name": {"type": "object"}},
        ),
        (
            {
                "name": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"subprop": {"type": "string"}},
                    },
                }
            },
            {
                "name": {
                    "type": "nested",
                    "properties": {"subprop": {"type": "keyword"}},
                }
            },
        ),
        (
            {"name": {"type": "array", "items": {"type": "string"}}},
            {"name": {"type": "keyword"}},
        ),
        (
            {"name": {"type": "array", "items": {"$ref": "foo"}}},
            {"name": {"type": "long"}},
        ),
        (
            {"name": {"type": "string"}, "additionalProperties": {"type": "integer"}},
            {"name": {"type": "keyword"}, "additionalProperties": {"type": "long"}},
        ),
        (
            {"name": {"type": "string"}, "additionalProperties": False},
            {"name": {"type": "keyword"}},
        ),
    ),
)
def test__convert_property(schema, mappings):
    assert (
        JSONSchemaToMappings(
            {
                "properties": {},
                "$defs": {"foo": {"type": "integer", "description": "a ref"}},
            }
        )._convert_property(schema)
        == mappings
    )


def test__convert_property_missing_type():
    with pytest.raises(SchemaParsingException) as e:
        JSONSchemaToMappings({"properties": {}})._convert_property(
            {"name": {"foo": "bar"}}
        )
    assert "Invalid schema, object missing type key" in str(e)


def test__convert_property_invalid_type():
    with pytest.raises(SchemaParsingException) as e:
        JSONSchemaToMappings({"properties": {}})._convert_property(
            {"name": {"type": "foo"}}
        )
    assert "Unknown property type 'foo'" in str(e)


def test__convert_property_array_missing_items():
    with pytest.raises(SchemaParsingException) as e:
        JSONSchemaToMappings({"properties": {}})._convert_property(
            {"name": {"type": "array"}}
        )
    assert "Invalid schema, array type missing items key" in str(e)


def test__convert_property_array_items_missing_type():
    with pytest.raises(SchemaParsingException) as e:
        JSONSchemaToMappings({"properties": {}})._convert_property(
            {"name": {"type": "array", "items": {"foo": "bar"}}}
        )
    assert "Invalid schema, array items object missing type key" in str(e)


def test__convert_property_array_items_invalid_type():
    with pytest.raises(SchemaParsingException) as e:
        JSONSchemaToMappings({"properties": {}})._convert_property(
            {"name": {"type": "array", "items": {"type": "array"}}}
        )
    assert "Unable to parse type 'array' within array" in str(e)
