import argparse
import json
from collections.abc import Mapping
from functools import cached_property
from typing import Any, Dict, Optional, Union

import fastjsonschema

# JSON schema constants
JS_TYPE_KEY = "type"
JS_PROPERTIES_KEY = "properties"
JS_ITEMS_KEY = "items"
JS_OBJECT_TYPE = "object"
JS_ARRAY_TYPE = "array"
JS_DEFS_KEY = "$defs"
JS_ID_KEY = "$id"
JS_REF_KEY = "$ref"
JS_DEF_REPLACE = "#/$defs/"
JS_ADDITIONAL_PROPERTIES_KEY = "additionalProperties"

# OpenSearch/Elasticsearch constants
OS_MAPPINGS_KEY = "mappings"
OS_PROPERTIES_KEY = "properties"
OS_TYPE_KEY = "type"
OS_NESTED_KEY = "nested"

TYPE_MAP = {
    "boolean": "boolean",
    "float": "float",
    "number": "float",
    "integer": "long",
    "string": "keyword",
    "object": "object",
}


class SchemaParsingException(Exception):
    pass


class JSONSchemaToMappings:
    """
    Class for converting a JSON schema document to an
    OpenSearch/ElasticSearch mappings document
    """

    def __init__(
        self, json_schema: Union[str, Dict], template: Optional[Union[str, Dict]] = None
    ):
        """
        Init method for conversion class

        :param json_schema: JSON file path or JSON schema as a dict
        :type json_schema: str or Dict
        :param template: template JSON mappings file or dict to add to
        :type template: str or Dict
        """
        self.json_schema = self._load_and_validate(json_schema)

        self.template = {}
        if template:
            if isinstance(template, str):
                self.template = self._load_json_doc(template)
            else:
                self.template = template

    def to_mappings(self):
        """
        Convert JSON schema to an OpenSearch/ElasticSearch mappings document

        :return: mappings dict
        :rtype: Dict
        """
        mappings = {
            OS_MAPPINGS_KEY: {
                OS_PROPERTIES_KEY: self._convert_property(
                    self.json_schema[JS_PROPERTIES_KEY]
                )
            }
        }

        # merge template
        return self._update_dict(self.template, mappings)

    def _load_and_validate(self, json_schema) -> Dict[str, Any]:
        """
        Loads/parses and validates given JSON schema (dict or JSON file)

        :return: JSON as dict
        :rtype: Dict
        """
        if isinstance(json_schema, str):
            json_schema = self._load_json_doc(json_schema)

        self._validate_json_schema(json_schema)

        return json_schema

    def _load_json_doc(self, json_schema_file) -> Dict[str, Any]:
        """
        Loads a JSON document file into a dict

        :return: JSON as dict
        :rtype: Dict
        """
        with open(json_schema_file, "rt") as f:
            return json.load(f)

    def _validate_json_schema(self, json_schema):
        """
        Validates a given JSON schema dict.
        Raises an exception if schema is not valid.

        :param json_schema: JSON schema as a dict
        :type json_schema: Dict
        """
        fastjsonschema.compile(json_schema)
        if JS_PROPERTIES_KEY not in json_schema:
            raise KeyError(f"Invalid schema, missing key '{JS_PROPERTIES_KEY}'")

    @cached_property
    def _defs(self) -> Dict:
        """
        Gets reference definitions from JSON schema

        :return: dict of reference definitions
        :rtype: Dict
        """
        return self.json_schema.get(JS_DEFS_KEY, {})

    @cached_property
    def _def_replace_key(self) -> str:
        """
        Gets the prefix string to replace in a definition reference

        :return: prefix string
        :rtype: str
        """
        return self.json_schema.get(JS_ID_KEY, "") + JS_DEF_REPLACE

    def _expand_def(self, o) -> Dict[str, Any]:
        """
        Expands an object from a definition reference

        :param o: dict/object to convert
        :type o: Dict
        :return: dict of OS mappings properties
        :rtype: Dict
        """
        ref_key = o[JS_REF_KEY].replace(self._def_replace_key, "")
        try:
            expanded = {**o, **self._defs[ref_key]}
        except KeyError:
            raise SchemaParsingException(
                f"Unable to find definition for reference '{ref_key}'"
            )
        del expanded[JS_REF_KEY]
        return expanded

    def _update_dict(self, d, u):
        """
        Recursively updates dict with values from another

        :param d: first dict
        :type d: Dict
        :param u: update dict, values overwrite first dict
        :type: u: dict
        """
        for k, v in u.items():
            if isinstance(v, Mapping):
                d[k] = self._update_dict(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    def _convert_property(self, o) -> Dict[str, Any]:
        """
        Recursively called method to convert JSON schema properties
        to OpenSearch/ElasticSearch mappings

        :param o: dict/object to convert
        :type o: Dict
        :return: dict of OS mappings properties
        :rtype: Dict
        """
        converted: Dict[str, Any] = {}

        for k in o:
            # "additionalProperties" (bool) is used in JSON schema to denote
            # if additional properties beyond those listed are permitted.
            # BUT it can also be a valid property key, so we need to check the type
            if k == JS_ADDITIONAL_PROPERTIES_KEY and isinstance(o[k], bool):
                continue

            # expand definition if ref is present
            if JS_REF_KEY in o[k]:
                o[k] = self._expand_def(o[k])

            # get type of this property
            t = o[k].get(JS_TYPE_KEY)
            if t is None:
                raise SchemaParsingException(
                    "Invalid schema, "
                    f"object missing type key '{JS_TYPE_KEY}': {json.dumps(o[k])}"
                )

            # object type (dict) - recurse
            if t == JS_OBJECT_TYPE and JS_PROPERTIES_KEY in o[k]:
                converted[k] = {
                    OS_PROPERTIES_KEY: self._convert_property(o=o[k][JS_PROPERTIES_KEY])
                }

            # array/list type
            elif t == JS_ARRAY_TYPE:
                converted[k] = self._convert_array(o[k])

            # element type e.g. string, integer
            elif t in TYPE_MAP:
                converted[k] = {OS_TYPE_KEY: TYPE_MAP[t]}

            # not trying to parse any other types
            else:
                raise SchemaParsingException(f"Unknown property type '{t}'")

        return converted

    def _convert_array(self, arr) -> Dict[str, Any]:
        """
        Factored out method for converting array types
        """
        converted: Dict[str, Any] = {}

        if JS_ITEMS_KEY not in arr:
            raise SchemaParsingException(
                f"Invalid schema, {JS_ARRAY_TYPE} type missing "
                f"{JS_ITEMS_KEY} key: {arr}"
            )

        # expand object described under items key
        if JS_REF_KEY in arr[JS_ITEMS_KEY]:
            arr[JS_ITEMS_KEY] = self._expand_def(arr[JS_ITEMS_KEY])

        # get type of array items
        at = arr[JS_ITEMS_KEY].get(JS_TYPE_KEY)
        if at is None:
            raise SchemaParsingException(
                f"Invalid schema, {JS_ARRAY_TYPE} items object missing "
                f"{JS_TYPE_KEY} key '{JS_TYPE_KEY}': "
                f"{json.dumps(arr[JS_ITEMS_KEY])}"
            )

        # if array items are themselves objects, mark as nested and recurse
        if at == JS_OBJECT_TYPE:
            converted[OS_TYPE_KEY] = OS_NESTED_KEY
            converted[OS_PROPERTIES_KEY] = self._convert_property(
                arr[JS_ITEMS_KEY][JS_PROPERTIES_KEY]
            )
        # if array items are elements, OS/ES does not denote this
        elif at in TYPE_MAP:
            converted[OS_TYPE_KEY] = TYPE_MAP[at]
        # TODO: deal with nested lists
        else:
            raise SchemaParsingException(
                f"Unable to parse type '{at}' within {JS_ARRAY_TYPE}: "
                f"{arr[JS_ITEMS_KEY]}"
            )

        return converted


def main():
    """
    Entrypoint for command line script
    """
    args = process_arguments()

    mappings = jsonschematomappings(args.json_schema[0], args.template)

    print(json.dumps(mappings, indent=2))


def process_arguments():
    """
    Define command line inputs
    """
    parser = argparse.ArgumentParser(
        description=(
            "Convert a JSON schema document to an "
            "OpenSearch/ElasticSearch mappings document"
        )
    )
    # Define the arguments that will be taken.
    parser.add_argument("json_schema", nargs=1, help="JSON schema document")
    parser.add_argument("--template", type=str, help="Template mappings document")
    return parser.parse_args()


def jsonschematomappings(
    json_schema: Union[str, Dict], template: Optional[Union[str, Dict]] = None
) -> Dict[str, Any]:
    """
    Wrapper method for functional users.
    Convert JSON schema to an OpenSearch/ElasticSearch mappings document.

    :param json_schema: JSON file path or JSON schema as a dict
    :type json_schema: str or Dict
    :param template: template JSON mappings file to add to
    :type template: str or Dict
    :return: mappings dict
    :rtype: Dict
    """
    return JSONSchemaToMappings(json_schema, template).to_mappings()


if __name__ == "__main__":
    main()
