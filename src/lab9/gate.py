"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, brows = pr.get("rows", []), base.get("rows", [])
    for mid, val in pr.get("metrics", {}).items():
        if isinstance(val, (int, float)) and not math.isfinite(val):
            problems.append(f"metric {mid} is non-finite")
    expected = pr.get("manifest", {}).get("items", 0) * len(pr.get("manifest", {}).get("seeds", []))
    if len(rows) != expected:
        problems.append(f"row count {len(rows)} != manifest items×seeds {expected}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    bkeys = [(r.get("item_id"), r.get("seed")) for r in brows]
    if len(set(keys)) != len(keys):
        problems.append("duplicate (item_id, seed) rows")
    if set(keys) != set(bkeys):
        problems.append("(item_id, seed) coverage differs from baseline")
    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures is non-empty")
    from lab9.graders import GRADERS
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for i, row in enumerate(rows):
        for mid in graded:
            if mid not in row or row[mid] is None:
                problems.append(f"row {i} missing/null graded metric {mid}")
                break
    bmap = {r.get("item_id"): r.get("slices") or [] for r in brows}
    for row in rows:
        if (row.get("slices") or []) != bmap.get(row.get("item_id"), []):
            problems.append(f"slice tags changed for {row.get('item_id')}")
            break
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        old = {m["id"]: m for m in base_spec.get("metrics", [])}
        new = {m["id"]: m for m in spec.get("metrics", [])}
        for mid, om in old.items():
            if mid not in new:
                problems.append(f"ratchet: metric {mid} removed")
                continue
            nm = new[mid]
            if om.get("blocking") and not nm.get("blocking"):
                problems.append(f"ratchet: metric {mid} made non-blocking")
            ot, nt = om.get("threshold", {}), nm.get("threshold", {})
            if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
                problems.append(f"ratchet: metric {mid} minimum loosened")
            if "max" in ot and ("max" not in nt or nt["max"] > ot["max"]):
                problems.append(f"ratchet: metric {mid} maximum loosened")
            if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
                problems.append(f"ratchet: metric {mid} removed no_significant_drop")
        old_s = {s["name"]: s for s in base_spec.get("slices", [])}
        new_s = {s["name"]: s for s in spec.get("slices", [])}
        for name, ospec in old_s.items():
            ns = new_s.get(name)
            if ns is None:
                problems.append(f"ratchet: slice {name} removed")
                continue
            if ospec.get("blocking") and not ns.get("blocking"):
                problems.append(f"ratchet: slice {name} made non-blocking")
            if "min" in ospec and ("min" not in ns or ns["min"] < ospec["min"]):
                problems.append(f"ratchet: slice {name} minimum loosened")
            if ospec.get("no_significant_drop") and not ns.get("no_significant_drop"):
                problems.append(f"ratchet: slice {name} removed no_significant_drop")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        name, metric = s["name"], s["metric"]
        a, b = per_item(pr, metric, name), per_item(base, metric, name)
        value = sum(a.values()) / len(a) if a else None
        verdict = False
        note = ""
        if value is None:
            verdict = True
            note = "no slice items"
        elif "min" in s and value < s["min"]:
            verdict = True
            note = f"mean {value:.3f} < {s['min']}"
        if s.get("no_significant_drop") and a and b:
            # Compare only same slice members; changes to labels are rejected by
            # integrity_check before this function is called.
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = (note + "; " if note else "") + f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            verdict = verdict or hi < 0
        ident = f"slice:{name}/{metric}"
        lines.append(f"  {ident:<32} {value!s:<8} {note:<35} {'BLOCK' if verdict and s.get('blocking') else 'ok'}")
        if verdict and s.get("blocking"):
            blocked.append(ident)
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
