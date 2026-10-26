"""Tests for scripts/opencode_config.py: the OpenCode config a run starts from (one model, no web tools, its base URL).

    python3 scripts/tests/test_opencode_config.py     # stdlib only
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import opencode_config as m  # noqa: E402

M = "anthropic/claude-opus-5-5"
GW = "http://172.17.0.1:4000/u/api.anthropic.com/v1"


class Config(unittest.TestCase):
    def test_default(self):
        self.assertEqual(m.config(M), {"small_model": M, "permission": {"webfetch": "deny", "websearch": "deny"}})

    def test_base_url(self):
        cfg = m.config(M, base_url=GW)
        self.assertEqual(cfg["provider"], {"anthropic": {"options": {"baseURL": GW}}})

    def test_web_search_allowed(self):
        self.assertEqual(m.config(M, web_search="allowed"), {"small_model": M})
        with self.assertRaises(ValueError):
            m.config(M, web_search="maybe")

    def test_overlay_is_kept(self):
        over = {"provider": {"anthropic": {"models": {"claude-opus-5-5": {"limit": {"context": 1000000, "output": 128000}}},
                                           "options": {"baseURL": "https://elsewhere.example/v1", "timeout": 600000}}},
                "permission": {"bash": "allow"}}
        cfg = m.config(M, over, base_url=GW)
        opts = cfg["provider"]["anthropic"]["options"]
        self.assertEqual(opts, {"baseURL": GW, "timeout": 600000})        # the runner's base URL replaces the overlay's
        self.assertEqual(cfg["provider"]["anthropic"]["models"], over["provider"]["anthropic"]["models"])
        self.assertEqual(cfg["permission"], {"bash": "allow", "webfetch": "deny", "websearch": "deny"})
        self.assertEqual(over["provider"]["anthropic"]["options"]["baseURL"], "https://elsewhere.example/v1")  # not mutated

    def test_overlay_that_denies_already(self):
        cfg = m.config(M, {"permission": {"webfetch": "deny"}, "tools": {"websearch": False}})
        self.assertEqual(cfg["permission"], {"webfetch": "deny", "websearch": "deny"})

    def test_refused(self):
        for over in ({"permission": {"webfetch": "allow"}}, {"permission": {"websearch": "ask"}},
                     {"permission": {"webfetch": {"*": "allow"}}}, {"tools": {"webfetch": True}},
                     {"permission": "allow"}, {"small_model": "anthropic/claude-haiku-5-5"}, ["not", "an", "object"]):
            with self.assertRaises(ValueError, msg=over):
                m.config(M, over)
        with self.assertRaises(ValueError):
            m.config("claude-opus-5-5")                                     # no provider
        with self.assertRaises(ValueError):
            m.config(M, {"provider": {"anthropic": "x"}}, base_url=GW)

    def test_allowed_web_tools_are_left_alone(self):
        self.assertEqual(m.config(M, {"permission": {"webfetch": "allow"}}, web_search="allowed")["permission"],
                         {"webfetch": "allow"})


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "opencode_config.py"), *args], capture_output=True, text=True)

    def test_one_line_that_harbor_parses(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"provider": {"anthropic": {"models": {"claude-opus-5-5": {"name": "Opus 5.5 test"}}}}}, f)
        r = self.run_cli(M, "--overlay", f.name, "--base-url", GW)
        pathlib.Path(f.name).unlink()
        self.assertEqual(r.returncode, 0, r.stderr)
        line = r.stdout.strip()
        self.assertEqual(r.stdout.count("\n"), 1)
        # Harbor's parse_kwargs reads an --ak value as JSON: the printed line is the dict the agent gets
        cfg = json.loads(line)
        self.assertEqual(cfg["provider"]["anthropic"]["options"]["baseURL"], GW)
        self.assertEqual(cfg["provider"]["anthropic"]["models"]["claude-opus-5-5"]["name"], "Opus 5.5 test")

    def test_refusal_exit_2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"permission": {"webfetch": "allow"}}, f)
        r = self.run_cli(M, "--overlay", f.name)
        pathlib.Path(f.name).unlink()
        self.assertEqual(r.returncode, 2)
        self.assertIn("permission.webfetch", r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.run_cli(M, "--overlay", "/nonexistent.json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
