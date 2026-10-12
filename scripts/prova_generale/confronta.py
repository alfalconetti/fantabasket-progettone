import json, sys
def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a: out.append((path + "/" + k, "—", b[k]))
            elif k not in b: out.append((path + "/" + k, a[k], "—"))
            else: out += diff(a[k], b[k], path + "/" + k)
    elif a != b:
        out.append((path, a, b))
    return out
for nome in ("main", "aste"):
    p = json.load(open(f"{sys.argv[1]}/prima_{nome}.json")); d = json.load(open(f"{sys.argv[1]}/dopo_{nome}.json"))
    dd = diff(p, d)
    print(f"== {nome}: {len(dd)} differenze")
    for path, x, y in dd: print(f"  {path}\n     prima: {json.dumps(x, ensure_ascii=False)[:300]}\n     dopo:  {json.dumps(y, ensure_ascii=False)[:300]}")
