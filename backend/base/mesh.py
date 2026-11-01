"""
mesh.py
Picks the image -> 3D backend and falls back to the next one when it fails.

Backends:
  hunyuan            Hunyuan3D-2mini on your GPU        (base/hunyuan.py)
  instantmesh_local  InstantMesh on your GPU            (base/instantmesh_local.py)
  instantmesh_api    InstantMesh HF Space, remote API   (base/instantmesh.py)

S2S_MESH is the order to try them in (comma separated). Default:
  hunyuan,instantmesh_local,instantmesh_api

A backend that is not set up on this machine (e.g. no S2S_IM_DIR) is skipped
without being tried. Use a single name (S2S_MESH=hunyuan) to turn the
fallback off.
"""

import logging
import os

log=logging.getLogger(__name__)

DEFAULT_CHAIN="hunyuan,instantmesh_local,instantmesh_api"
LABELS={
    "hunyuan":"Hunyuan3D (local)(Plain Mesh - Fast)",
    "instantmesh_local":"InstantMesh (local)(LowRes - Slowest)",
    "instantmesh_api":"InstantMesh (API)(HighRes - Fastest)",
}
# "instantmesh" is the old S2S_MESH value and always meant the HF Space
ALIASES={"instantmesh":"instantmesh_api","im_api":"instantmesh_api","im_local":"instantmesh_local","hy":"hunyuan"}


class Unavailable(Exception):
    """The backend is not installed or configured here (not a failure while running)."""


class AllFailed(RuntimeError):
    """Every backend in the chain failed or was skipped. failures=[(label,exception),...]"""

    def __init__(self,failures):
        self.failures=failures
        super().__init__("; ".join(f"{label}: {err}" for label,err in failures))


def chain():
    """The backend names to try, in order, from S2S_MESH."""
    raw=os.getenv("S2S_MESH") or DEFAULT_CHAIN
    names=[]
    for part in raw.lower().split(","):
        name=ALIASES.get(part.strip(),part.strip())
        if name and name not in names:
            names.append(name)
    if not names or any(n not in LABELS for n in names):
        raise ValueError(f"S2S_MESH={raw!r} is not valid. Use a comma separated list of: {', '.join(LABELS)}")
    return names


def choices():
    """What the UI offers: auto (the S2S_MESH order) plus each backend on its own."""
    from pathlib import Path
    im_dir=os.getenv("S2S_IM_DIR","").strip()
    im_ready=bool(im_dir) and (Path(im_dir)/"run.py").is_file()
    ready={"hunyuan":True,"instantmesh_local":im_ready,"instantmesh_api":True}
    why={"instantmesh_local":"" if im_ready else "Set S2S_IM_DIR to enable"}
    items=[{"id":"auto","label":"Auto (with fallback)","available":True,"note":" > ".join(LABELS[n] for n in chain())}]
    for name,label in LABELS.items():
        items.append({"id":name,"label":label,"available":ready[name],"note":why.get(name,"")})
    return items


def resolve(choice):
    """The chain to run for a UI choice. "auto" or empty means the S2S_MESH order."""
    choice=ALIASES.get((choice or "").strip().lower(),(choice or "").strip().lower())
    if choice in("","auto"):
        return chain()
    if choice not in LABELS:
        raise ValueError(f"Unknown 3D backend {choice!r}. Use auto or one of: {', '.join(LABELS)}")
    return[choice]


def _load(name):
    # imported on demand: each backend pulls in different libraries
    if name=="hunyuan":
        from base.hunyuan import run_hunyuan
        return run_hunyuan
    if name=="instantmesh_local":
        from base.instantmesh_local import run_instantmesh_local
        return run_instantmesh_local
    from base.instantmesh import run_instantmesh
    return run_instantmesh


def make_mesh(image,job_dir,on_stage=None,choice=None):
    """Returns (mesh_path,backend_name) from the first backend that works.

    choice: a backend name to use alone (no fallback), or None/"auto" for the S2S_MESH order.
    """
    say=on_stage or(lambda _:None)
    failures=[]
    note=""
    for name in resolve(choice):
        label=LABELS[name]

        def step(text,note=note):
            say(note+text)

        try:
            path=_load(name)(image,job_dir,on_stage=step)
        except Unavailable as exc:
            log.info("%s skipped: %s",label,exc)
            failures.append((label,exc))
        except Exception as exc:
            log.warning("%s failed: %s",label,exc)
            failures.append((label,exc))
            note=f"{label} failed. "
        else:
            if failures:
                log.info("%s was used after %d other backend(s) failed or were skipped",label,len(failures))
            return path,name
    if len(failures)==1:
        raise failures[0][1]   # one backend configured: report its own error
    raise AllFailed(failures)