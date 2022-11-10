# jsonschematomappings

Convert JSON schema to OpenSearch/ElasticSearch mappings

## Install

From pypi:

```
pip install jsonschematomappings
```

From repository directory:

```
pip install -e .
```

If developing/running tests:

```
pip install -r requirements/requirements-test.txt
```

## Run

```
$ jsonschematomappings -h
usage: jsonschematomappings [-h] [--template TEMPLATE] json_schema

Convert a JSON schema document to an OpenSearch/ElasticSearch mappings document

positional arguments:
  json_schema          JSON schema document

optional arguments:
  -h, --help           show this help message and exit
  --template TEMPLATE  Template mappings document
```
