"""Tests for Validator complexity limits."""

import pytest

from a2e_lang.parser import parse
from a2e_lang.validator import Validator


class TestMaxOperations:

    def test_within_limit(self):
        v = Validator(max_operations=5)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        ''')
        assert v.validate(w) == []

    def test_exceeds_limit(self):
        v = Validator(max_operations=2)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        c = Wait { duration: 3 }
        ''')
        errors = v.validate(w)
        assert any("3 operations" in str(e) and "maximum allowed is 2" in str(e) for e in errors)

    def test_exact_limit(self):
        v = Validator(max_operations=2)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        ''')
        assert v.validate(w) == []

    def test_no_limit_by_default(self):
        v = Validator()
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        c = Wait { duration: 3 }
        d = Wait { duration: 4 }
        e = Wait { duration: 5 }
        ''')
        assert v.validate(w) == []


class TestMaxConditions:

    def test_within_limit(self):
        v = Validator(max_conditions=3)
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/data
            where a == 1, b == 2
            -> /workflow/out
        }
        ''')
        assert v.validate(w) == []

    def test_exceeds_limit(self):
        v = Validator(max_conditions=1)
        w = parse('''
        workflow "t"
        f = FilterData {
            from /workflow/data
            where a == 1, b == 2, c == 3
            -> /workflow/out
        }
        ''')
        errors = v.validate(w)
        assert any("3 conditions" in str(e) and "maximum allowed is 1" in str(e) for e in errors)


class TestMaxDepth:

    def test_single_conditional_depth_1(self):
        v = Validator(max_depth=1)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/x > 0
            then a
            else b
        }
        ''')
        assert v.validate(w) == []

    def test_depth_exceeds_limit(self):
        v = Validator(max_depth=1)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        inner = Conditional {
            if /workflow/x > 0
            then a
        }
        outer = Conditional {
            if /workflow/y > 0
            then inner
        }
        ''')
        errors = v.validate(w)
        assert any("nesting depth 2" in str(e) and "maximum allowed is 1" in str(e) for e in errors)

    def test_combined_limits(self):
        v = Validator(max_operations=10, max_depth=3, max_conditions=5)
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/x > 0
            then a
            else b
        }
        ''')
        assert v.validate(w) == []
