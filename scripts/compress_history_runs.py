import argparse
import json
import re
import shutil
from pathlib import Path


RUN_SNAPSHOT_RE = re.compile(r"^\d{8}_\d{6}(?:_[0-9a-fA-F]{6})?\.json$")


def trunc_str(s, max_chars: int) -> str:
    if not isinstance(s, str):
        return s
    if max_chars and len(s) > max_chars:
        return s[:max_chars] + f"\n...[truncated {len(s) - max_chars} chars]"
    return s


def slim_ports(arr, max_chars: int):
    out = []
    if not isinstance(arr, list):
        return out
    for it in arr:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("Kind", "") or "")
        d = {"name": it.get("name"), "Kind": it.get("Kind")}
        if "String" in kind:
            d["Context"] = trunc_str(it.get("Context"), max_chars)
        elif "Boolean" in kind:
            d["Boolean"] = it.get("Boolean")
        elif "Num" in kind:
            d["Num"] = it.get("Num")
        out.append(d)
    return out


def slim_nodes(nodes, max_chars: int):
    slim = []
    if not isinstance(nodes, list):
        return slim
    for n in nodes:
        if not isinstance(n, dict):
            continue
        slim.append(
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "label": n.get("label"),
                "NodeKind": n.get("NodeKind"),
                "isFinish": n.get("isFinish"),
                "IsError": n.get("IsError"),
                "ErrorContext": trunc_str(n.get("ErrorContext"), max_chars),
                "Inputs": slim_ports(n.get("Inputs", []), max_chars),
                "Outputs": slim_ports(n.get("Outputs", []), max_chars),
            }
        )
    return slim


def main():
    ap = argparse.ArgumentParser(description="Compress History run snapshots by slimming node payload + truncating long strings.")
    ap.add_argument("--history-root", default="History", help="History directory root (default: History)")
    ap.add_argument("--max-chars", type=int, default=4000, help="Max chars per string field (default: 4000)")
    ap.add_argument("--dry-run", action="store_true", help="Only report what would be changed")
    args = ap.parse_args()

    root = Path(args.history_root)
    if not root.exists():
        raise SystemExit(f"History root not found: {root}")

    changed = 0
    scanned = 0
    for fp in root.rglob("*.json"):
        scanned += 1
        if not RUN_SNAPSHOT_RE.match(fp.name):
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        nodes = None
        if isinstance(data.get("nodes"), list):
            nodes = data.get("nodes")
        elif isinstance(data.get("nodes"), dict) and isinstance(data["nodes"].get("nodes"), list):
            nodes = data["nodes"]["nodes"]
        if not isinstance(nodes, list):
            continue

        slim_payload = {
            "project": fp.parent.name,
            "saved_at": data.get("saved_at"),
            "nodes": slim_nodes(nodes, args.max_chars),
        }

        if args.dry_run:
            changed += 1
            print(f"[DRY] would compress: {fp}")
            continue

        bak = fp.with_suffix(fp.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(fp, bak)
        fp.write_text(json.dumps(slim_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        changed += 1
        print(f"[OK] compressed: {fp} (backup: {bak.name})")

    print(f"Done. scanned={scanned}, compressed={changed}")


if __name__ == "__main__":
    main()


