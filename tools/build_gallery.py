#!/usr/bin/env python3
"""
Build a static gallery of every job in backend/base/outputs/.

Run it again whenever new jobs appear and the gallery grows with them. The GitHub
Action in .github/workflows/gallery.yml does this automatically on every push.

    python tools/build_gallery.py --markdown         # -> GALLERY.md (shows on GitHub, no hosting)
    python tools/build_gallery.py                    # -> _site/index.html (open on your PC)
    python tools/build_gallery.py --no-models        # skip copying .glb files
    python tools/build_gallery.py --outputs PATH --out PATH

Only needs the standard library. If Pillow is installed, small .webp thumbnails
are generated so the page loads fast; otherwise the original PNGs are used.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGES = [
    ("sketch", "Sketch"),
    ("control", "Control map"),
    ("rendered", "Render"),
    ("foreground", "Cutout"),
]
THUMB = 520


def git_time(folder: Path):
    """Last commit time of a job folder (mtimes are meaningless after a git checkout)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(folder)],
            capture_output=True, text=True, cwd=ROOT, timeout=15,
        ).stdout.strip()
        return int(out) if out else None
    except Exception:
        return None


def job_time(folder: Path) -> int:
    t = git_time(folder)
    if t:
        return t
    stamps = [p.stat().st_mtime for p in folder.iterdir() if p.is_file()]
    return int(max(stamps)) if stamps else int(folder.stat().st_mtime)


def make_thumb(src: Path, dst: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(src) as im:
            im.thumbnail((THUMB, THUMB))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            im.save(dst, "WEBP", quality=82, method=4)
        return True
    except Exception as e:
        print(f"  thumb failed for {src.name}: {e}", file=sys.stderr)
        return False


def collect(outputs: Path, site: Path, copy_models: bool):
    jobs = []
    for folder in sorted(p for p in outputs.iterdir() if p.is_dir()):
        present = {k: folder / f"{k}.png" for k, _ in STAGES if (folder / f"{k}.png").is_file()}
        if not present:
            continue  # empty / unfinished job folder
        meta = {}
        jf = folder / "job.json"
        if jf.is_file():
            try:
                meta = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                pass

        jid = folder.name
        dest = site / "jobs" / jid
        dest.mkdir(parents=True, exist_ok=True)

        images, thumbs = {}, {}
        for key, src in present.items():
            shutil.copy2(src, dest / src.name)
            images[key] = f"jobs/{jid}/{src.name}"
            t = dest / f"{key}.thumb.webp"
            thumbs[key] = f"jobs/{jid}/{t.name}" if make_thumb(src, t) else images[key]

        model = None
        glb = folder / "model.glb"
        if copy_models and glb.is_file() and glb.stat().st_size > 0:
            shutil.copy2(glb, dest / "model.glb")
            model = f"jobs/{jid}/model.glb"

        jobs.append({
            "id": jid,
            "prompt": (meta.get("prompt") or "").strip(),
            "kind": meta.get("kind") or "sketch",
            "seed": meta.get("seed"),
            "images": images,
            "thumbs": thumbs,
            "model": model,
            "has3d": bool(model) or glb.is_file(),
            "time": job_time(folder),
        })
    jobs.sort(key=lambda j: (-j["time"], j["id"]))
    return jobs


def build_markdown(outputs: Path, target: Path):
    """Write GALLERY.md. Images are referenced in place, nothing is copied."""
    import html as _html
    import os
    base = target.parent
    rel = lambda p: os.path.relpath(p, base).replace(os.sep, "/")
    rows = []
    for folder in sorted(p for p in outputs.iterdir() if p.is_dir()):
        present = {k: folder / f"{k}.png" for k, _ in STAGES if (folder / f"{k}.png").is_file()}
        if not present:
            continue
        meta = {}
        jf = folder / "job.json"
        if jf.is_file():
            try:
                meta = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                pass
        glb = folder / "model.glb"
        rows.append({
            "id": folder.name,
            "prompt": (meta.get("prompt") or "").strip(),
            "kind": meta.get("kind") or "sketch",
            "present": present,
            "glb": glb if glb.is_file() and glb.stat().st_size > 0 else None,
            "time": job_time(folder),
        })
    rows.sort(key=lambda j: (-j["time"], j["id"]))

    out = ["# Gallery", "",
           f"Every run from `backend/base/outputs/` ({len(rows)} so far, "
           f"{sum(1 for r in rows if r['glb'])} with a 3D model). Newest first.", "",
           "This page is generated by `python tools/build_gallery.py --markdown`. "
           "Click any image to see it full size.", ""]
    for r in rows:
        name = _html.escape(r["prompt"]) if r["prompt"] else ("Photo, no prompt" if r["kind"] == "photo" else "No prompt")
        out += [f"### {name}", "",
                f"`{r['id']}` · {r['kind']}" + (f" · [model.glb]({rel(r['glb'])}) (download)" if r["glb"] else " · no 3D model"), "",
                "| " + " | ".join(label for k, label in STAGES) + " |",
                "|" + "---|" * len(STAGES)]
        cells = []
        for k, label in STAGES:
            if k in r["present"]:
                u = rel(r["present"][k])
                cells.append(f'<a href="{u}"><img src="{u}" width="200" alt="{label}" /></a>')
            else:
                cells.append("not made")
        out += ["| " + " | ".join(cells) + " |", ""]
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"Gallery: {len(rows)} runs -> {target}")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sketch2Shape AI · Gallery</title>
<script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@3.5.0/dist/model-viewer.min.js"></script>
<style>
:root{
  --bg:#f6f6f9; --surface:#fff; --text:#1b1b22; --muted:#6a6a78; --line:#e3e3ea;
  --accent:#7064dc; --accent2:#5bc8b2; --check1:#eceff3; --check2:#fff; --shadow:0 1px 3px rgba(0,0,0,.08);
  color-scheme: light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#101015; --surface:#1a1a22; --text:#ececf3; --muted:#9b9bab; --line:#2b2b36;
    --check1:#23232c; --check2:#1a1a22; --shadow:none; color-scheme: dark;
  }
}
:root[data-theme="dark"]{
  --bg:#101015; --surface:#1a1a22; --text:#ececf3; --muted:#9b9bab; --line:#2b2b36;
  --check1:#23232c; --check2:#1a1a22; --shadow:none; color-scheme: dark;
}
*{box-sizing:border-box}
html,body{margin:0}
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{padding:40px 20px 8px;max-width:1200px;margin:0 auto}
h1{margin:0 0 4px;font-size:28px;letter-spacing:-.02em}
h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);margin:0}
.bar{max-width:1200px;margin:18px auto 0;padding:0 20px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.chip{border:1px solid var(--line);background:var(--surface);color:var(--text);padding:6px 14px;border-radius:999px;cursor:pointer;font:inherit;font-size:14px}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.count{margin-left:auto;color:var(--muted);font-size:14px}
input[type=search]{border:1px solid var(--line);background:var(--surface);color:var(--text);padding:7px 12px;border-radius:999px;font:inherit;font-size:14px;min-width:160px}
main{max-width:1200px;margin:18px auto 60px;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;cursor:pointer;box-shadow:var(--shadow);transition:transform .15s,border-color .15s;text-align:left;padding:0;font:inherit;color:inherit}
.card:hover,.card:focus-visible{transform:translateY(-3px);border-color:var(--accent);outline:none}
.cover{aspect-ratio:1;position:relative;background:conic-gradient(var(--check1) 25%,var(--check2) 0 50%,var(--check1) 0 75%,var(--check2) 0) 0 0/20px 20px}
.cover img{width:100%;height:100%;object-fit:contain;display:block}
.cover img.inset{position:absolute;left:8px;bottom:8px;width:64px;height:64px;border-radius:8px;border:2px solid var(--surface);background:#fff;object-fit:cover;box-shadow:0 1px 4px rgba(0,0,0,.25)}
.badge3d{position:absolute;right:8px;top:8px;background:var(--accent);color:#fff;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px}
.meta{padding:10px 12px 12px}
.title{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.small{color:var(--muted);font-size:12.5px;font-family:ui-monospace,Consolas,monospace}
.empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:60px 0}
dialog{border:none;border-radius:16px;padding:0;max-width:min(960px,94vw);width:100%;background:var(--surface);color:var(--text);box-shadow:0 20px 60px rgba(0,0,0,.4)}
dialog::backdrop{background:rgba(0,0,0,.6)}
.dhead{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line)}
.dhead h2{margin:0;font-size:18px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.x{border:none;background:none;color:var(--muted);font-size:26px;cursor:pointer;line-height:1}
.stages{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;padding:16px 20px}
.stage figure{margin:0}
.stage .img{aspect-ratio:1;border-radius:10px;border:1px solid var(--line);overflow:hidden;background:conic-gradient(var(--check1) 25%,var(--check2) 0 50%,var(--check1) 0 75%,var(--check2) 0) 0 0/16px 16px}
.stage img{width:100%;height:100%;object-fit:contain;display:block}
.stage figcaption{margin-top:6px;font-size:13px;color:var(--muted);display:flex;justify-content:space-between}
.stage a{color:var(--accent);text-decoration:none}
.viewer{padding:0 20px 20px}
.viewer model-viewer{width:100%;height:380px;border-radius:12px;background:var(--bg);border:1px solid var(--line);--poster-color:transparent}
.viewer .row{display:flex;gap:12px;align-items:center;margin-top:8px;font-size:13px;color:var(--muted)}
.viewer .row a{color:var(--accent);text-decoration:none;font-weight:600}
</style>
</head>
<body>
<header>
  <h1><span>Sketch2Shape AI</span> · Gallery</h1>
  <p class="sub">Every run from <code>backend/base/outputs/</code>, stage by stage. Click a card to open it.</p>
</header>
<div class="bar">
  <button class="chip" data-f="all" aria-pressed="true">All</button>
  <button class="chip" data-f="3d" aria-pressed="false">With 3D model</button>
  <button class="chip" data-f="sketch" aria-pressed="false">Sketches</button>
  <button class="chip" data-f="photo" aria-pressed="false">Photos</button>
  <input type="search" id="q" placeholder="Search prompt or id" aria-label="Search">
  <span class="count" id="count"></span>
</div>
<main id="grid"></main>

<dialog id="dlg">
  <div class="dhead"><h2 id="dtitle"></h2><button class="x" id="dx" aria-label="Close">&times;</button></div>
  <div class="stages" id="dstages"></div>
  <div class="viewer" id="dviewer"></div>
</dialog>

<script>
const JOBS = /*__DATA__*/[];
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const LABELS = {sketch:"Sketch", control:"Control map", rendered:"Render", foreground:"Cutout"};
let filter = "all", query = "";

function title(j){ return j.prompt || (j.kind === "photo" ? "Photo (no prompt)" : "No prompt"); }

function render(){
  const q = query.trim().toLowerCase();
  const list = JOBS.filter(j =>
    (filter === "all" || (filter === "3d" ? j.has3d : j.kind === filter)) &&
    (!q || (j.prompt + " " + j.id).toLowerCase().includes(q)));
  $("count").textContent = list.length + " of " + JOBS.length + " runs";
  $("grid").innerHTML = list.length ? list.map(j => {
    const cover = j.thumbs.foreground || j.thumbs.rendered || j.thumbs.sketch;
    const inset = j.thumbs.sketch && cover !== j.thumbs.sketch
      ? `<img class="inset" src="${esc(j.thumbs.sketch)}" alt="" loading="lazy">` : "";
    return `<button class="card" data-id="${esc(j.id)}">
      <div class="cover"><img src="${esc(cover)}" alt="${esc(title(j))}" loading="lazy">${inset}
      ${j.has3d ? '<span class="badge3d">3D</span>' : ""}</div>
      <div class="meta"><div class="title">${esc(title(j))}</div>
      <div class="small">${esc(j.id)} · ${esc(j.kind)}</div></div></button>`;
  }).join("") : '<div class="empty">No runs match.</div>';
}

function openJob(id){
  const j = JOBS.find(x => x.id === id); if (!j) return;
  $("dtitle").textContent = title(j) + "  ·  " + j.id;
  $("dstages").innerHTML = Object.keys(LABELS).filter(k => j.images[k]).map(k => `
    <div class="stage"><figure><div class="img"><img src="${esc(j.thumbs[k])}" alt="${LABELS[k]}"></div>
    <figcaption><span>${LABELS[k]}</span><a href="${esc(j.images[k])}" target="_blank" rel="noopener">full size</a></figcaption></figure></div>`).join("");
  $("dviewer").innerHTML = j.model
    ? `<model-viewer src="${esc(j.model)}" camera-controls auto-rotate shadow-intensity="0.6" alt="3D model"></model-viewer>
       <div class="row"><span>Drag to rotate, scroll to zoom.</span><a href="${esc(j.model)}" download>Download .glb</a></div>`
    : "";
  $("dlg").showModal();
}

document.querySelectorAll(".chip").forEach(b => b.onclick = () => {
  filter = b.dataset.f;
  document.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", c === b));
  render();
});
$("q").oninput = e => { query = e.target.value; render(); };
$("grid").onclick = e => { const c = e.target.closest(".card"); if (c) openJob(c.dataset.id); };
$("dx").onclick = () => $("dlg").close();
$("dlg").onclick = e => { if (e.target === $("dlg")) $("dlg").close(); };
$("dlg").addEventListener("close", () => { $("dviewer").innerHTML = ""; });
render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", type=Path, default=ROOT / "backend" / "base" / "outputs")
    ap.add_argument("--out", type=Path, default=ROOT / "_site")
    ap.add_argument("--markdown", nargs="?", const=str(ROOT / "GALLERY.md"), default=None, metavar="PATH",
                    help="write a Markdown gallery (default GALLERY.md) instead of the HTML site")
    ap.add_argument("--no-models", action="store_true", help="do not copy model.glb files")
    args = ap.parse_args()

    if not args.outputs.is_dir():
        sys.exit(f"outputs folder not found: {args.outputs}")

    if args.markdown:
        build_markdown(args.outputs, Path(args.markdown))
        return

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    jobs = collect(args.outputs, args.out, copy_models=not args.no_models)

    data = json.dumps(jobs, ensure_ascii=False).replace("</", "<\\/")
    (args.out / "index.html").write_text(PAGE.replace("/*__DATA__*/[]", data), encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out / ".nojekyll").write_text("")

    size = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file()) / 1e6
    print(f"Gallery: {len(jobs)} runs, {sum(1 for j in jobs if j['model'])} with 3D models, {size:.1f} MB -> {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
