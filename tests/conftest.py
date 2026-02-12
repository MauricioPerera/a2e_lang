"""Shared fixtures for a2e-lang tests."""

import pytest

from a2e_lang.compiler import Compiler
from a2e_lang.parser import parse
from a2e_lang.validator import Validator


@pytest.fixture
def compiler():
    return Compiler()


@pytest.fixture
def validator():
    return Validator()


# ---------------------------------------------------------------------------
# Sample DSL sources
# ---------------------------------------------------------------------------

MINIMAL_WORKFLOW = '''
workflow "minimal"

fetch = ApiCall {
  method: "GET"
  url: "https://api.example.com/data"
  -> /workflow/result
}
'''

SIMPLE_WORKFLOW = '''
workflow "simple-test"

fetch_users = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  headers: { Authorization: credential("api-token") }
  -> /workflow/users
}

filter_active = FilterData {
  from /workflow/users
  where status == "active", points > 100
  -> /workflow/filtered
}

run: fetch_users -> filter_active
'''

FULL_WORKFLOW = '''
workflow "full-pipeline"

# API call
fetch_users = ApiCall {
  method: "GET"
  url: "https://api.example.com/users"
  headers: { Authorization: credential("api-key"), "Content-Type": "application/json" }
  timeout: 30000
  -> /workflow/users
}

# Transform
extract = TransformData {
  from /workflow/users
  transform: "select"
  config: { field: "data.users" }
  -> /workflow/extracted
}

# Filter
filter_active = FilterData {
  from /workflow/extracted
  where status == "active", points > 100
  -> /workflow/filtered
}

# Conditional
check = Conditional {
  if /workflow/filtered > 0
  then store_result
  else log_empty
}

# Store
store_result = StoreData {
  from /workflow/filtered
  storage: "localStorage"
  key: "active-users"
}

log_empty = StoreData {
  from /workflow/filtered
  storage: "localStorage"
  key: "empty-result"
}

# Merge
merged = MergeData {
  sources: [/workflow/filtered, /workflow/users]
  strategy: "deepMerge"
  -> /workflow/merged
}

# Wait
pause = Wait {
  duration: 5000
}

# Loop
process_each = Loop {
  from /workflow/filtered
  operations: [fetch_users]
  -> /workflow/loop_results
}

run: fetch_users -> extract -> filter_active -> check
'''


@pytest.fixture
def minimal_source():
    return MINIMAL_WORKFLOW


@pytest.fixture
def simple_source():
    return SIMPLE_WORKFLOW


@pytest.fixture
def full_source():
    return FULL_WORKFLOW


@pytest.fixture
def minimal_ast():
    return parse(MINIMAL_WORKFLOW)


@pytest.fixture
def simple_ast():
    return parse(SIMPLE_WORKFLOW)


@pytest.fixture
def full_ast():
    return parse(FULL_WORKFLOW)
