"""Tests for the workflow simulator."""

from a2e_lang.parser import parse
from a2e_lang.simulator import Simulator


class TestBasicSimulation:

    def test_all_operations_executed(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 100 }
        b = Wait { duration: 200 }
        run: a -> b
        ''')
        sim = Simulator()
        result = sim.simulate(w)
        assert result.operations_executed == ["a", "b"]
        assert result.skipped == []

    def test_wait_produces_warning(self):
        w = parse('''
        workflow "t"
        pause = Wait { duration: 5000 }
        ''')
        sim = Simulator()
        result = sim.simulate(w)
        assert any("5000ms" in w for w in result.warnings)

    def test_summary_output(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 100 }
        ''')
        sim = Simulator()
        result = sim.simulate(w)
        s = result.summary()
        assert "Operations executed: 1" in s
        assert "a" in s


class TestApiCallSimulation:

    def test_api_call_with_mock_data(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            -> /workflow/users
        }
        ''')
        sim = Simulator()
        mock = {"/workflow/users": [{"name": "Alice"}, {"name": "Bob"}]}
        result = sim.simulate(w, input_data=mock)
        assert "fetch" in result.operations_executed
        assert result.paths_written["/workflow/users"] == mock["/workflow/users"]

    def test_api_call_without_mock_creates_placeholder(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com"
            -> /workflow/data
        }
        ''')
        sim = Simulator()
        result = sim.simulate(w)
        assert "/workflow/data" in result.paths_written
        assert any("placeholder" in w for w in result.warnings)


class TestFilterSimulation:

    def test_filter_with_data(self):
        w = parse('''
        workflow "t"
        fetch = ApiCall { method: "GET" url: "https://x.com" -> /workflow/users }
        filter = FilterData {
            from /workflow/users
            where status == "active"
            -> /workflow/filtered
        }
        run: fetch -> filter
        ''')
        sim = Simulator()
        mock = {
            "/workflow/users": [
                {"name": "Alice", "status": "active"},
                {"name": "Bob", "status": "inactive"},
                {"name": "Carol", "status": "active"},
            ]
        }
        result = sim.simulate(w, input_data=mock)
        filtered = result.paths_written["/workflow/filtered"]
        assert len(filtered) == 2
        assert all(u["status"] == "active" for u in filtered)


class TestConditionalSimulation:

    def test_condition_true_branch(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/count > 0
            then a
            else b
        }
        run: check
        ''')
        sim = Simulator()
        result = sim.simulate(w, input_data={"/workflow/count": 5})
        assert "check" in result.operations_executed
        assert "a" in result.operations_executed
        assert "b" not in result.operations_executed
        assert any("then" in b for b in result.branches_taken)

    def test_condition_false_branch(self):
        w = parse('''
        workflow "t"
        a = Wait { duration: 1 }
        b = Wait { duration: 2 }
        check = Conditional {
            if /workflow/count > 0
            then a
            else b
        }
        run: check
        ''')
        sim = Simulator()
        result = sim.simulate(w, input_data={"/workflow/count": 0})
        assert "check" in result.operations_executed
        assert "b" in result.operations_executed
        assert "a" not in result.operations_executed
        assert any("else" in b for b in result.branches_taken)


class TestFullPipeline:

    def test_e2e_simulation(self):
        w = parse('''
        workflow "user-pipeline"

        fetch = ApiCall {
            method: "GET"
            url: "https://api.example.com/users"
            -> /workflow/users
        }

        filter = FilterData {
            from /workflow/users
            where status == "active", points > 100
            -> /workflow/filtered
        }

        store = StoreData {
            from /workflow/filtered
            storage: "localStorage"
            key: "results"
        }

        run: fetch -> filter -> store
        ''')
        sim = Simulator()
        mock = {
            "/workflow/users": [
                {"name": "Alice", "status": "active", "points": 150},
                {"name": "Bob", "status": "inactive", "points": 200},
                {"name": "Carol", "status": "active", "points": 50},
                {"name": "Dave", "status": "active", "points": 300},
            ]
        }
        result = sim.simulate(w, input_data=mock)
        assert result.operations_executed == ["fetch", "filter", "store"]
        filtered = result.paths_written["/workflow/filtered"]
        assert len(filtered) == 2
        assert {u["name"] for u in filtered} == {"Alice", "Dave"}
