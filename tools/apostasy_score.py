"""The Modlist Manager scored against a hand-built reference list: does it pick the SAME WINNER as the list's author where
it matters in game? (The owner, 2026-09-26: "So what can we do to increase the percentage of likeness and is it
functionally meaningful" - the answer was that only conflicts matter, so they are what this scores.)

The reference is Apostasy 3.2.0 as its author shipped it: the OLDEST backups of the profile's lists (memory:
apostasy-original-order-is-oldest-backup), read-only. A scratch instance under %TEMP% holds one junction per author mod
(pointing at the folder that holds it now - its own name or the owner's renamed "[NoDelete] 00xx" copy) and a profile
whose modlist is the author's SHUFFLED (fixed seed), so nothing can score by keeping today's order. Then the offline dry
run, and three numbers:

  files    - of the files two enabled mods both ship, the share where the run's winner is the author's (by files)
  records  - of the records two or more plugins override, the share where the run's winning plugin is the author's
  pairs    - of ALL mod pairs, the share in the author's relative order (reported, not gated: 99.9% of pairs never
             conflict, so their order is cosmetic)

    python tools\\apostasy_score.py            score; exit 1 if files or records fall more than 0.1 point below the baseline
    python tools\\apostasy_score.py --accept   score and record it as the new baseline (tools\\apostasy-baseline.json)

Gate: tools\\selfcheck.py runs this after the launch audit when the Apostasy instance exists.
"""
import _winapi, json, os, random, re, shutil, struct, subprocess, sys, tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(HERE, "tools", "apostasy-baseline.json")
args = sys.argv[1:]


def opt(k, d):
    return args[args.index(k) + 1] if k in args else d


SRC = opt("--instance", r"C:\Modlists\Apostasy")
PROFILE = opt("--profile", "Apostasy")
STAMP_LIST, STAMP_PLUG = "2026_04_05_02_15_33", "2026_04_05_02_15_32"
WORK = opt("--work", os.path.join(tempfile.gettempdir(), "mm-apostasy-reference"))
SEED = 26
TOLERANCE = 0.1


def read_rows(text):
    rows = [(l[1:], l[0] == "+") for l in text.splitlines() if l[:1] in ("+", "-")]
    rows.reverse()
    return rows


# --- the scratch instance ------------------------------------------------------------------------------------------------
src_prof = os.path.join(SRC, "profiles", PROFILE)
author_modlist = os.path.join(src_prof, f"modlist.txt.{STAMP_LIST}")
if not os.path.isfile(author_modlist):
    print(f"SKIP  no author modlist at {author_modlist}")
    sys.exit(0)
prof = os.path.join(WORK, "profiles", "Shuffled")
os.makedirs(prof, exist_ok=True)
for f in ("categories.dat", "nexuscatmap.dat", "ModOrganizer.ini"):
    if os.path.isfile(os.path.join(SRC, f)):
        shutil.copy2(os.path.join(SRC, f), os.path.join(WORK, f))
text = open(author_modlist, encoding="utf-8-sig").read()
lines = text.splitlines()
head = [l for l in lines if l.startswith("#")]
body = [l for l in lines if l[:1] in ("+", "-")]
random.Random(SEED).shuffle(body)
open(os.path.join(prof, "modlist.txt"), "wb").write(("\r\n".join(head + body) + "\r\n").encode("utf-8"))
for f in ("plugins.txt", "loadorder.txt"):
    shutil.copy2(os.path.join(src_prof, f"{f}.{STAMP_PLUG}"), os.path.join(prof, f))
sg = os.path.join(WORK, "Stock Game")
if not os.path.exists(sg) and os.path.isdir(os.path.join(SRC, "Stock Game")):
    _winapi.CreateJunction(os.path.join(SRC, "Stock Game"), sg)
mods_dir = os.path.join(WORK, "mods")
os.makedirs(mods_dir, exist_ok=True)


def norm_name(n):
    n = re.sub(r"^\[nodelete\]\s*\d*\s*", "", n.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()


live = os.listdir(os.path.join(SRC, "mods"))
by_norm = defaultdict(list)
for f in live:
    by_norm[norm_name(f)].append(f)
author = read_rows(text)
missing = 0
for n, _en in author:
    if n.endswith("_separator"):
        continue
    dst = os.path.join(mods_dir, n)
    if os.path.exists(dst):
        continue
    src = os.path.join(SRC, "mods", n) if n in live else None
    if src is None:
        c = by_norm.get(norm_name(n), [])
        src = os.path.join(SRC, "mods", c[0]) if len(c) == 1 else None
    if src is None:
        missing += 1
        continue
    _winapi.CreateJunction(src, dst)

# --- the dry run ---------------------------------------------------------------------------------------------------------
cache = os.path.join(WORK, "cache")
os.makedirs(cache, exist_ok=True)
r = subprocess.run([sys.executable, os.path.join(HERE, "MO2ModlistManager.py"), WORK, "Shuffled", cache], capture_output=True, text=True)
if r.returncode != 0:
    print(f"FAIL  the dry run failed\n{r.stdout[-600:]}{r.stderr[-600:]}")
    sys.exit(1)
run = json.load(open(os.path.join(cache, "dry-run.json"), encoding="utf-8"))
# A separator the plan creates must not differ only in letter case from one it retires: on Windows they are the same
# folder, so Apply made the new one and then moved it away with the old (2026-09-26, "Player homes" / "Player Homes")
_retired = {s.lower() for s in run["facts"]["retired"]}
_clash = [s for s in run["facts"]["created"] if s.lower() in _retired]
if _clash:
    print(f"FAIL  separators created and retired under the same folder name (case only): {'; '.join(_clash)}")
    sys.exit(1)

# --- scoring -------------------------------------------------------------------------------------------------------------
enabled = [n for n, e in author if e and not n.endswith("_separator") and os.path.isdir(os.path.join(mods_dir, n))]
a_pos = {n: i for i, n in enumerate(enabled)}
r_pos = {n: i for i, (n, _e) in enumerate(run["rows"])}
SKIP_TOP = {"fomod", "docs", "readme", "readmes", "source", "optional"}
SKIP_EXT = (".txt", ".md", ".pdf", ".url", ".html", ".jpg", ".psd", ".log")
owners, plugin_path = defaultdict(list), {}
for n in enabled:
    d = os.path.join(mods_dir, n)
    for dp, dn, fn in os.walk(d):
        rel = os.path.relpath(dp, d).replace("\\", "/").lower()
        if (rel.split("/")[0] if rel != "." else "") in SKIP_TOP:
            dn[:] = []
            continue
        for f in fn:
            lf = f.lower()
            if rel == "." and lf.endswith((".esp", ".esm", ".esl")):
                plugin_path[lf] = os.path.join(dp, f)
                continue
            if lf == "meta.ini" or lf.endswith(SKIP_EXT) or (rel == "." and lf.endswith((".bsa", ".ini"))):
                continue
            owners[rel + "/" + lf if rel != "." else lf].append(n)
same_f = all_f = 0
for f, os_ in owners.items():
    os_ = [o for o in os_ if o in r_pos]
    if len(os_) < 2:
        continue
    all_f += 1
    if max(os_, key=a_pos.get) == max(os_, key=r_pos.get):
        same_f += 1


def scan(path):
    data = open(path, "rb").read()
    if data[:4] != b"TES4":
        return [], []
    size = struct.unpack_from("<I", data, 4)[0]
    masters, off, end = [], 24, 24 + size
    while off < end:
        st, sl = struct.unpack_from("<4sH", data, off)
        if st == b"MAST":
            masters.append(data[off + 6:off + 6 + sl].rstrip(b"\0").decode("cp1252", "replace").lower())
        off += 6 + sl
    recs, n = [], len(data)
    while off + 24 <= n:
        t = data[off:off + 4]
        sz = struct.unpack_from("<I", data, off + 4)[0]
        if t == b"GRUP":
            off += 24
            continue
        recs.append((t, struct.unpack_from("<I", data, off + 12)[0]))
        off += 24 + sz
    return masters, recs


rec_owners = defaultdict(set)
for p, path in plugin_path.items():
    try:
        masters, recs = scan(path)
    except (OSError, struct.error):
        continue
    for t, fid in recs:
        if (fid >> 24) < len(masters) and t not in (b"NAVM", b"LAND", b"CELL", b"WRLD", b"PGRE", b"PHZD"):
            rec_owners[(masters[fid >> 24], fid & 0xFFFFFF)].add(p)
a_lo = {x.strip().lower(): i for i, x in enumerate(open(os.path.join(prof, "loadorder.txt"), encoding="utf-8", errors="replace"))
        if x.strip() and not x.startswith("#")}
r_lo = {p.lower(): i for i, p in enumerate(run["plugins"])}
same_r = all_r = 0
for ps in rec_owners.values():
    ps = [p for p in ps if p in a_lo and p in r_lo]
    if len(ps) < 2:
        continue
    all_r += 1
    if max(ps, key=a_lo.get) == max(ps, key=r_lo.get):
        same_r += 1


def inversions(a):
    if len(a) < 2:
        return a, 0
    m = len(a) // 2
    l, x = inversions(a[:m])
    rr, y = inversions(a[m:])
    out, i, j, inv = [], 0, 0, x + y
    while i < len(l) and j < len(rr):
        if l[i] <= rr[j]:
            out.append(l[i]); i += 1
        else:
            out.append(rr[j]); j += 1; inv += len(l) - i
    return out + l[i:] + rr[j:], inv


seq = [r_pos[n] for n in enabled if n in r_pos]
tot = len(seq) * (len(seq) - 1) // 2
score = {"files": round(100.0 * same_f / max(1, all_f), 2), "records": round(100.0 * same_r / max(1, all_r), 2),
         "pairs": round(100.0 * (1 - inversions(seq)[1] / max(1, tot)), 2),
         "contested_files": all_f, "contested_records": all_r, "mods": len(enabled), "unresolved_mods": missing}
print(f"Apostasy reference (author's 3.2.0 order, shuffled seed {SEED}): files {score['files']}%  records {score['records']}%  "
      f"pairs {score['pairs']}%  ({all_f} contested files, {all_r} contested records, {len(enabled)} mods)")
base = json.load(open(BASELINE, encoding="utf-8")) if os.path.isfile(BASELINE) else None
if "--accept" in args or base is None:
    json.dump(score, open(BASELINE, "w", encoding="utf-8"), indent=1)
    print(f"baseline {'recorded' if base is None else 'accepted'}: {BASELINE}")
    sys.exit(0)
bad = [k for k in ("files", "records") if score[k] < base[k] - TOLERANCE]
for k in ("files", "records", "pairs"):
    print(f"  {k:8s} {score[k]:6.2f}%  (baseline {base[k]:.2f}%)")
if bad:
    print(f"FAIL  {', '.join(bad)} fell below the baseline: a change made the manager pick different winners than the author "
          f"where it matters in game. Find the flipped pairs before accepting (--accept) a lower score.")
    sys.exit(1)
print("PASS  no fall in contested-winner agreement")
