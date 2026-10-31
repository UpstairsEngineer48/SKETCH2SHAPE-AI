"""
app.py
Flask backend for Sketch2Shape AI.

  POST /api/generate            -> 202 {job_id}  (starts a background job)
  GET  /api/jobs/<job_id>       -> status, progress text, model_url when done
  GET  /api/files/<job_id>/<n>  -> generated files (model.glb, rendered.png ...)
  GET  /api/health              -> model/GPU status for the UI indicator

Every route also works WITHOUT the /api prefix, so it is correct whether or
not the Vite dev proxy strips "/api".

Pipeline per job:
  preprocessing -> controlnet (SD1.5) -> background_removal -> instantmesh
"""

import logging
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint,Flask,jsonify,request,send_from_directory
from flask_cors import CORS
from PIL import Image

from base import controlnet
from base.export import error_response

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("sketch2shape")

app=Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"]=20*1024*1024

OUTPUTS=Path(__file__).parent/"base"/"outputs"
OUTPUTS.mkdir(parents=True,exist_ok=True)

TOTAL_STEPS=4
JOB_TTL_SECONDS=6*3600
MIME={".glb":"model/gltf-binary",".obj":"text/plain",".png":"image/png"}

JOBS={}
JOBS_LOCK=threading.Lock()
RUN_LOCK=threading.Lock()   # one GPU pipeline at a time

bp=Blueprint("api",__name__)


# -- helpers ----------------------------------------------------------------

def _update(job_id,**fields):
    with JOBS_LOCK:
        JOBS[job_id].update(fields)
        JOBS[job_id]["updated"]=time.time()


def _friendly(exc):
    """Turn library exceptions into messages a user can act on."""
    text=f"{type(exc).__name__}: {exc}"
    low=text.lower()
    if isinstance(exc,ValueError):
        return str(exc)
    if "quota" in low or "zerogpu" in low:
        return ("The free Hugging Face GPU quota for InstantMesh is used up. "
                "Set HF_TOKEN (a free access token) before starting the backend, or try again later.")
    if "out of memory" in low:
        return "The GPU ran out of memory. Start the backend with S2S_LOW_VRAM=1."
    if any(w in low for w in("connecterror","connection","timeout","name resolution","max retries")):
        return ("Could not reach Hugging Face. Check your internet connection and that "
                "the TencentARC/InstantMesh Space is running.")
    return text[:400]


def _cleanup_old_jobs():
    cutoff=time.time()-JOB_TTL_SECONDS
    for d in OUTPUTS.iterdir():
        if d.is_dir() and d.stat().st_mtime<cutoff:
            shutil.rmtree(d,ignore_errors=True)
    with JOBS_LOCK:
        for jid in[j for j,v in JOBS.items() if v["created"]<cutoff]:
            del JOBS[jid]


def _run_job(job_id,sketch_path,prompt):
    # imported here so Flask starts instantly (rembg/onnxruntime are heavy)
    from base.preprocessing import preprocess_sketch
    from base.background_removal import remove_background
    from base.instantmesh import run_instantmesh

    job_dir=OUTPUTS/job_id
    _update(job_id,status="queued",label="Waiting for the previous job to finish")
    with RUN_LOCK:
        started=time.time()
        try:
            _update(job_id,status="running",step=1,label="Reading your sketch")
            control,kind=preprocess_sketch(sketch_path,job_dir/"control.png")
            log.info("Job %s | input treated as %s",job_id,kind)

            loaded=controlnet.status()["loaded"]
            _update(job_id,step=2,label="Rendering the object from your sketch" if loaded
                    else "Loading the image model (first run downloads several GB)")
            rendered=controlnet.sketch_to_image(control,prompt,job_dir/"rendered.png")
            log.info("Job %s | rendered in %.0fs",job_id,time.time()-started)
            _update(job_id,preview_url=f"/files/{job_id}/rendered.png")

            _update(job_id,step=3,label="Cutting out the object")
            cutout=remove_background(rendered,job_dir/"foreground.png")

            _update(job_id,step=4,label="Building the 3D mesh")
            mesh=run_instantmesh(cutout,job_dir,on_stage=lambda t:_update(job_id,label=t))

            _update(job_id,status="done",label="Done",
                    model_url=f"/files/{job_id}/{mesh.name}",
                    format=mesh.suffix.lstrip("."),
                    filename=f"sketch2shape_{job_id}{mesh.suffix}")
            log.info("Job %s | finished in %.0fs",job_id,time.time()-started)
        except Exception as exc:
            log.exception("Job %s | failed",job_id)
            _update(job_id,status="error",error=_friendly(exc))


# -- routes -----------------------------------------------------------------

@bp.get("/health")
def health():
    st=controlnet.status()
    return jsonify({
        "status":"error" if st["error"] else "ok",
        "model_loaded":st["loaded"],
        "loading":st["loading"],
        "device":st["device"],
        "fast_mode":st["fast"],
        "error":st["error"],
    })


@bp.post("/generate")
def generate():
    upload=request.files.get("image")
    if upload is None or not upload.filename:
        return error_response("No image file provided.",400)

    prompt=(request.form.get("prompt") or "").strip()[:400] or "a clean 3D object"
    job_id=uuid.uuid4().hex[:12]
    job_dir=OUTPUTS/job_id
    job_dir.mkdir(parents=True)
    sketch_path=job_dir/"sketch.png"
    upload.save(sketch_path)

    try:
        with Image.open(sketch_path) as probe:
            probe.verify()
    except Exception:
        shutil.rmtree(job_dir,ignore_errors=True)
        return error_response("That file is not a readable image.",400)

    _cleanup_old_jobs()
    now=time.time()
    with JOBS_LOCK:
        JOBS[job_id]={"job_id":job_id,"status":"queued","step":0,"total_steps":TOTAL_STEPS,
                      "label":"Queued","created":now,"updated":now}
    log.info("Job %s | prompt=%r",job_id,prompt)
    threading.Thread(target=_run_job,args=(job_id,sketch_path,prompt),daemon=True).start()
    return jsonify({"job_id":job_id,"status":"queued"}),202


@bp.get("/jobs/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job=JOBS.get(job_id)
        data=dict(job) if job else None
    if data is None:
        return error_response("Unknown job. The server may have restarted.",404)
    data["elapsed"]=round(time.time()-data["created"])
    return jsonify(data)


@bp.get("/files/<job_id>/<path:name>")
def files(job_id,name):
    if not re.fullmatch(r"[0-9a-f]{12}",job_id):
        return error_response("Not found.",404)
    return send_from_directory(OUTPUTS/job_id,name,mimetype=MIME.get(Path(name).suffix.lower()))


app.register_blueprint(bp,url_prefix="/api")
app.register_blueprint(bp,name="api_root")


# -- startup ----------------------------------------------------------------

def _preload():
    try:
        controlnet.load()
    except Exception:
        pass   # reported through /health; the next job retries


threading.Thread(target=_preload,daemon=True).start()

if __name__=="__main__":
    # use_reloader=False: the debug reloader would load the models twice
    app.run(host="127.0.0.1",port=8000,debug=False,threaded=True,use_reloader=False)
