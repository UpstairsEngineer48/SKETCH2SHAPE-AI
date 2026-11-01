"""
post.py
Optional clean-up of the exported .glb, run after validation:
  1. drop tiny floating pieces (< S2S_MIN_PART of the biggest piece, default 0.01)
  2. centre the mesh at the origin and scale its longest side to 1
  3. decimate to S2S_MAX_FACES (default 100000) when it has no colours

The untouched file is kept as model_raw.glb. If anything goes wrong the raw
mesh stays as model.glb, so this step can never fail a job.
S2S_POST=0 turns it off. Meshes with a texture image are left alone.
"""
import logging
import os
from pathlib import Path
from base.validate import MeshInvalid,load_mesh,validate_mesh

log=logging.getLogger(__name__)

ON=os.getenv("S2S_POST","1")=="1"
MAX_FACES=int(os.getenv("S2S_MAX_FACES","100000"))
MIN_PART=float(os.getenv("S2S_MIN_PART","0.01"))


def _drop_specks(m):
    parts=m.split(only_watertight=False)
    if len(parts)<2:
        return m,0
    top=max(len(p.faces) for p in parts)
    keep=[p for p in parts if len(p.faces)>=MIN_PART*top]
    if len(keep)==len(parts):
        return m,0
    import trimesh
    return (keep[0] if len(keep)==1 else trimesh.util.concatenate(keep)),len(parts)-len(keep)


def clean_mesh(path):
    """Rewrites model.glb in place. Returns the new stats dict, or None when skipped."""
    path=Path(path)
    if not ON or path.suffix.lower()!=".glb":
        return None
    try:
        m=load_mesh(path)
        if m.visual.kind=="texture":
            log.info("Post-processing skipped: the mesh has a texture image")
            return None
        n0=len(m.faces)
        m,gone=_drop_specks(m)
        if m.visual.kind is None and len(m.faces)>MAX_FACES:
            try:
                m=m.simplify_quadric_decimation(face_count=MAX_FACES)
            except Exception as exc:
                log.warning("Decimation skipped (pip install fast-simplification): %s",exc)
        elif len(m.faces)>MAX_FACES:
            log.info("Decimation skipped: it would drop the vertex colours")
        m.apply_translation(-(m.bounds[0]+m.bounds[1])/2)
        m.apply_scale(1.0/float((m.bounds[1]-m.bounds[0]).max()))
        tmp=path.with_name("model_post.glb")
        m.export(tmp)
        stats=validate_mesh(tmp)
        raw=path.with_name("model_raw.glb")
        os.replace(path,raw)
        os.replace(tmp,path)
        stats["raw_faces"]=n0
        stats["specks_removed"]=gone
        log.info("Post-processed: %d -> %d faces, %d speck(s) removed",n0,stats["faces"],gone)
        return stats
    except Exception as exc:
        log.warning("Post-processing failed, keeping the raw mesh: %s",exc)
        try:
            path.with_name("model_post.glb").unlink(missing_ok=True)
        except Exception:
            pass
        return None