"""validate.py: open the exported mesh and check it is real 3D geometry."""
import os
import numpy as np
import trimesh


class MeshInvalid(ValueError):
    pass


def load_mesh(path):
    """Open a .glb/.obj as ONE Trimesh, or raise MeshInvalid with a readable reason."""
    try:
        got=trimesh.load(path,force=None,process=False)
    except Exception as exc:
        raise MeshInvalid(f"The exported file could not be opened: {exc}") from exc
    if isinstance(got,trimesh.Scene):
        gs=[g for g in got.geometry.values() if isinstance(g,trimesh.Trimesh)]
        if not gs:
            raise MeshInvalid("The exported file contains no mesh geometry.")
        return gs[0] if len(gs)==1 else trimesh.util.concatenate(gs)
    if not isinstance(got,trimesh.Trimesh):
        raise MeshInvalid("The exported file does not contain a triangle mesh.")
    return got


def look_of(m):
    """'textured', 'vertex_colors' or 'shape_only' for an already loaded mesh."""
    vis=m.visual
    mat=getattr(vis,"material",None)
    if vis.kind=="texture" and (getattr(mat,"image",None) is not None or getattr(mat,"baseColorTexture",None) is not None):
        return "textured"
    return "vertex_colors" if vis.kind in("vertex","face") else "shape_only"


def validate_mesh(path):
    """Return a small stats dict, or raise MeshInvalid with a readable reason."""
    m=load_mesh(path)
    v=np.asarray(m.vertices)
    f=np.asarray(m.faces)
    if len(v)<4 or len(f)<4:
        raise MeshInvalid("The mesh is empty or has too few faces.")
    if not np.isfinite(v).all():
        raise MeshInvalid("The mesh contains NaN or infinite vertices.")
    ext=m.bounds[1]-m.bounds[0]
    if (ext<=1e-6).any():
        raise MeshInvalid("The mesh is flat along one axis (not real 3D volume).")
    look=look_of(m)
    return {
        "vertices":int(len(v)),
        "faces":int(len(f)),
        "extent":[round(float(x),4) for x in ext],
        "watertight":bool(m.is_watertight),
        "look":look,
        "has_texture":look=="textured",
        "has_vertex_colors":look=="vertex_colors",
        "file_bytes":int(os.path.getsize(path)),
    }