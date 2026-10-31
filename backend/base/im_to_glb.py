"""
im_to_glb.py
Runs inside the InstantMesh environment (started by instantmesh_local.py).

  python im_to_glb.py <model.obj> <model.glb>

InstantMesh's run.py saves the mesh in the raw model frame, while the HF Space
permutes the axes (vertices[:,[1,2,0]]) before writing its .glb. This gives the
local result the same orientation, so both routes look alike in the viewer.
(Derived from InstantMesh's run.py + mesh_util.save_obj and app.py + mesh_util.save_glb.)
"""

import sys

import numpy as np
import trimesh


def main(src,dst):
    mesh=trimesh.load(src,force="mesh",process=False)
    v=np.asarray(mesh.vertices)
    f=np.asarray(mesh.faces)
    out=trimesh.Trimesh(
        vertices=np.column_stack([-v[:,1],-v[:,2],-v[:,0]]),
        faces=f[:,::-1],
        vertex_colors=mesh.visual.vertex_colors,
        process=False,
    )
    out.export(dst,"glb")


if __name__=="__main__":
    main(sys.argv[1],sys.argv[2])
