"""Gli script GAS (gas/*.gs) provati con node e finti oggetti di Google: tests/gas/<nome>.js prova
gas/<nome>.gs. Senza node le prove si saltano."""
import os, shutil, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
node = shutil.which("node")
if not node:
    print("⚠️ node non c'è: prove degli script GAS saltate")
for f in sorted(os.listdir(os.path.join(ROOT, "tests", "gas"))) if node else []:
    gs = os.path.join(ROOT, "gas", f.replace(".js", ".gs"))
    r = subprocess.run([node, os.path.join(ROOT, "tests", "gas", f), gs], capture_output=True, text=True, timeout=60)
    print(r.stdout.strip() or f"❌ FAIL {f}: {r.stderr.strip()[:300]}")
