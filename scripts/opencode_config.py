#!/usr/bin/env python3
"""The OpenCode config a run passes as `--ak opencode_config=` (PROTOCOL D11, §2.11; scripts/run_agent_batch.sh).

    scripts/opencode_config.py <provider>/<model> [--overlay <opencode.json>] [--base-url <url>] [--web-search disabled|allowed]

Harbor's `opencode` agent writes ~/.config/opencode/opencode.json from the model (its provider and an empty model entry)
and deep-merges `opencode_config` over it. What this script puts there, measured on OpenCode 1.19.4 (2026-10-26, the
request bodies of a capture-only fake API):
  small_model  the run's own model. Without it OpenCode names each session with a second model of the provider
               (claude-haiku-5-5 for anthropic/), a call Harbor's token count leaves out and the run's key must be
               allowed to make;
  permission   webfetch and websearch "deny" (--web-search disabled, the default): a denied tool is not offered to the
               model at all (the request's tools lose webfetch; websearch is off by default and stays off). Under the
               egress allowlist webfetch would only fail; the deny keeps the tool list the same on tasks with open egress;
  baseURL      provider.<provider>.options.baseURL = --base-url, when given: the usage gateway's route or the configured
               upstream, in OpenCode's form (the AI SDK appends /messages or /responses to it, so Anthropic's ends in /v1).
--overlay is the caller's own OpenCode config (JSON, AGENT_CONFIG), merged first. One that allows webfetch or websearch
under --web-search disabled, or names another small_model, is refused (exit 2), never overridden silently; its baseURL
is replaced by --base-url. Prints the config as one compact JSON line."""
import argparse
import json
import sys

WEB_TOOLS = ("webfetch", "websearch")


def merge(base, over):
    """`over` deep-merged into `base` (dicts recursively, anything else replaced), as Harbor merges opencode_config."""
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def config(model, overlay=None, base_url=None, web_search="disabled"):
    """The opencode_config for `model` (<provider>/<model>); ValueError for a config an official run cannot start from."""
    if "/" not in model:
        raise ValueError(f"{model!r}: OpenCode's model is <provider>/<model>")
    if overlay is not None and not isinstance(overlay, dict):
        raise ValueError("the overlay is not a JSON object")
    provider = model.split("/", 1)[0]
    cfg = merge({"small_model": model}, json.loads(json.dumps(overlay or {})))
    if cfg["small_model"] != model:
        raise ValueError(f"the config sets small_model = {cfg['small_model']!r}; a run uses its own model, {model!r}")
    if web_search == "disabled":
        perm, tools = cfg.get("permission"), cfg.get("tools")
        if not isinstance(perm, (dict, type(None))) or not isinstance(tools, (dict, type(None))):
            raise ValueError("the config's permission / tools are not objects; write them per tool")
        for t in WEB_TOOLS:
            if (perm or {}).get(t) not in (None, "deny"):
                raise ValueError(f"the config sets permission.{t} = {perm[t]!r}; an official run denies it")
            if (tools or {}).get(t) not in (None, False):
                raise ValueError(f"the config sets tools.{t} = {tools[t]!r}; an official run turns it off")
        cfg["permission"] = {**(perm or {}), **{t: "deny" for t in WEB_TOOLS}}
    elif web_search != "allowed":
        raise ValueError(f"web search {web_search!r}: disabled or allowed")
    if base_url:
        entry = cfg.setdefault("provider", {}).setdefault(provider, {})
        if not isinstance(entry, dict) or not isinstance(entry.setdefault("options", {}), dict):
            raise ValueError(f"the config's provider.{provider} is not an object with an options object")
        entry["options"]["baseURL"] = base_url
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("model")
    ap.add_argument("--overlay")
    ap.add_argument("--base-url")
    ap.add_argument("--web-search", default="disabled")
    a = ap.parse_args(argv)
    try:
        overlay = json.load(open(a.overlay)) if a.overlay else None
        cfg = config(a.model, overlay, a.base_url, a.web_search)
    except (OSError, ValueError) as e:            # json.JSONDecodeError is a ValueError
        print(f"opencode_config: {e}", file=sys.stderr)
        return 2
    print(json.dumps(cfg, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
