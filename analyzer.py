"""BreakCheck core engine: AST-based Python API surface extraction & diff."""
import ast
from pathlib import Path
from surface import discover_public_api


LEVEL_RANK = {"patch": 0, "minor": 1, "major": 2}


def extract_api(source_dir):
    """Extract public API surface from all .py files in a directory tree."""
    surface = {"functions": {}, "classes": {}}
    for py_file in sorted(Path(source_dir).rglob("*.py")):
        mod = py_file.relative_to(source_dir).with_suffix("").as_posix().replace("/", ".")
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        public_names = discover_public_api(tree, str(py_file))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name in public_names:
                surface["functions"][f"{mod}.{node.name}"] = _parse_fn(node)
            elif isinstance(node, ast.ClassDef) and node.name in public_names:
                surface["classes"][f"{mod}.{node.name}"] = _parse_cls(node)

            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                surface["classes"][f"{mod}.{node.name}"] = _parse_cls(node)
    return surface


def _parse_fn(node):
    params = []
    for a in node.args.args:
        if a.arg == "self":
            continue
        ann = ast.unparse(a.annotation) if a.annotation else ""
        params.append({"name": a.arg, "ann": ann, "default": ""})
    for i, d in enumerate(node.args.defaults):
        idx = len(params) - len(node.args.defaults) + i
        if 0 <= idx < len(params):
            params[idx]["default"] = ast.unparse(d)
    ret = ast.unparse(node.returns) if node.returns else ""
    return {"params": params, "ret": ret}


def _parse_cls(node):
    methods, attrs = {}, []
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
            methods[item.name] = _parse_fn(item)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            attrs.append(item.target.id)
    return {"methods": methods, "attrs": attrs}


def _ch(kind, sym, detail, level):
    return {"kind": kind, "symbol": sym, "detail": detail, "level": level}


def diff_api(old, new):
    """Diff two API surfaces, returning list of classified changes."""
    changes = []
    for k, v in old["functions"].items():
        if k not in new["functions"]:
            changes.append(_ch("function_removed", k, f"Removed: {k}", "major"))
        else:
            changes += _diff_fn(k, v, new["functions"][k])
    for k in new["functions"]:
        if k not in old["functions"]:
            changes.append(_ch("function_added", k, f"Added: {k}", "minor"))
    for k, v in old["classes"].items():
        if k not in new["classes"]:
            changes.append(_ch("class_removed", k, f"Removed: {k}", "major"))
        else:
            changes += _diff_cls(k, v, new["classes"][k])
    for k in new["classes"]:
        if k not in old["classes"]:
            changes.append(_ch("class_added", k, f"Added: {k}", "minor"))
    return changes


def _diff_fn(sym, old, new):
    ch = []
    op = {p["name"]: p for p in old["params"]}
    np_ = {p["name"]: p for p in new["params"]}
    for n, p in op.items():
        if n not in np_:
            ch.append(_ch("param_removed", f"{sym}({n})", f"Param '{n}' removed from {sym}", "major"))
            continue
        q = np_[n]
        if p["ann"] and q["ann"] and p["ann"] != q["ann"]:
            ch.append(_ch("type_changed", f"{sym}({n})", f"Type of '{n}': {p['ann']} -> {q['ann']}", "major"))
        if p["default"] and not q["default"]:
            ch.append(_ch("default_removed", f"{sym}({n})", f"Default of '{n}' removed (now required)", "major"))
        elif p["default"] and q["default"] and p["default"] != q["default"]:
            ch.append(_ch("default_changed", f"{sym}({n})", f"Default of '{n}' changed", "patch"))
    for n in np_:
        if n not in op:
            lv = "minor" if np_[n]["default"] else "major"
            tag = "optional" if lv == "minor" else "REQUIRED"
            ch.append(_ch("param_added", f"{sym}({n})", f"Param '{n}' added ({tag})", lv))
    if old["ret"] and new["ret"] and old["ret"] != new["ret"]:
        ch.append(_ch("return_type_changed", sym, f"Return: {old['ret']} -> {new['ret']}", "major"))
    return ch


def _diff_cls(sym, old, new):
    ch = []
    for a in old["attrs"]:
        if a not in new["attrs"]:
            ch.append(_ch("attr_removed", f"{sym}.{a}", f"Attribute '{a}' removed from {sym}", "major"))
    for m, v in old["methods"].items():
        if m not in new["methods"]:
            ch.append(_ch("method_removed", f"{sym}.{m}", f"Method '{m}' removed from {sym}", "major"))
        else:
            ch += _diff_fn(f"{sym}.{m}", v, new["methods"][m])
    for m in new["methods"]:
        if m not in old["methods"]:
            ch.append(_ch("method_added", f"{sym}.{m}", f"Method '{m}' added to {sym}", "minor"))
    return ch


def max_level(changes):
    """Return the highest semver level among all changes."""
    if not changes:
        return "patch"
    return max((c["level"] for c in changes), key=lambda l: LEVEL_RANK[l])
