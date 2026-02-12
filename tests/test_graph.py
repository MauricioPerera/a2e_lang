"""Tests for graph visualization (Mermaid output)."""

from a2e_lang.graph import generate_mermaid
from a2e_lang.parser import parse


class TestMermaidGeneration:

    def test_basic_structure(self):
        w = parse('''
        workflow "t"
        a = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = generate_mermaid(w)
        assert result.startswith("graph TD")
        assert "a" in result
        assert "ApiCall" in result

    def test_data_flow_edges(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall { method: "GET" url: "https://x.com" -> /workflow/data }
        filter = FilterData {
            from /workflow/data
            where status == "active"
            -> /workflow/filtered
        }
        ''')
        result = generate_mermaid(w)
        assert "fetch -->|/workflow/data| filter" in result

    def test_conditional_edges(self):
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
        result = generate_mermaid(w)
        assert "check -->|then| a" in result
        assert "check -->|else| b" in result

    def test_execution_order_edges(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        run: a -> b
        ''')
        result = generate_mermaid(w)
        assert "a -.->|next| b" in result

    def test_styles_applied(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall { method: "GET" url: "https://x.com" -> /workflow/out }
        ''')
        result = generate_mermaid(w)
        assert "style fetch" in result

    def test_conditional_diamond_shape(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        check = Conditional {
            if /workflow/x > 0
            then a
        }
        ''')
        result = generate_mermaid(w)
        # Diamond shape uses { }
        assert "check{" in result or "check {" in result

    def test_multiple_operations(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall { method: "GET" url: "https://x.com" -> /workflow/users }
        filter = FilterData {
            from /workflow/users
            where active == true
            -> /workflow/filtered
        }
        store = StoreData {
            from /workflow/filtered
            storage: "localStorage"
            key: "data"
        }
        run: fetch -> filter -> store
        ''')
        result = generate_mermaid(w)
        # All nodes present
        assert "fetch" in result
        assert "filter" in result
        assert "store" in result
        # Execution order
        assert "fetch -.->|next| filter" in result
        assert "filter -.->|next| store" in result
