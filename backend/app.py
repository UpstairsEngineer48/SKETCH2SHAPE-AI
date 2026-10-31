"""
app.py
Flask backend for Sketch2Shape AI.

  POST /api/generate            -> 202 {job_id}  (starts a background job)
  GET  /api/jobs/<job_id>       -> status, progress text, model_url + mesh_stats when done
  POST /api/jobs/<job_id>/cancel -> stops the job (status becomes "cancelled")
  GET  /api/files/<job_id>/<n>  -> generated files (model.glb, rendered.png ...)
  GET  /api/health              -> model/GPU status for the UI indicator
  POST /api/client-log          -> browser log events, written to logs/frontend.log

Every route also works WITHOUT the /api prefix, so it is correct whether or
not the Vite dev proxy strips "/api".

Pipeline per job:
  preprocessing -> controlnet (SD1.5) -> background_removal -> mesh -> validate -> clean-up
  mesh = tried in order until one works (S2S_MESH, see base/mesh.py):
         InstantMesh (local) -> InstantMesh (HF Space API) -> Hunyuan3D-2mini (local, shape only)
  validate = the exported file is opened and checked (base/validate.py)
  clean-up = drop specks, centre, unit scale, decimate (base/post.py, S2S_POST=0 to skip)
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint,Flask,jsonify,request,send_from_directory
from flask_cors import CORS
from PIL import Image

from base import cancel,controlnet,logs
from base.export import error_response
from base.mesh import AllFailed,Unavailable,chain,choices,make_mesh,resolve
from base.post import clean_mesh

logs.setup()
log=logging.getLogger("sketch2shape")
client_log=logging.getLogger("sketch2shape.client")

app=Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"]=20*1024*1024

OUTPUTS=Path(__file__).parent/"base"/"outputs"
OUTPUTS.mkdir(parents=True,exist_ok=True)

TOTAL_STEPS=4
PHOTO_DIRECT=os.getenv("S2S_PHOTO_DIRECT","1")=="1"   # photos skip the sketch->image model
JOB_TTL_SECONDS=6*3600
SEED=int(os.getenv("S2S_SEED","42"))   # default seed; a request can send its own
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
    if isinstance(exc,AllFailed):
        parts=[]
        for label,err in exc.failures:
            msg=" ".join(_friendly(err).split())   # one line; the real error is at the end of a traceback
            parts.append(f"{label}: {msg if len(msg)<=220 else '...'+msg[-220:]}")
        return " | ".join(parts)
    if isinstance(exc,Unavailable):
        return str(exc)
    text=f"{type(exc).__name__}: {exc}"
    low=text.lower()
    if isinstance(exc,ValueError):
        return str(exc)
    if "hy3dgen" in low and "no module" in low:
        return "Hunyuan3D is not installed in that Python env. Set S2S_HY_PYTHON to its python.exe (see README)."
    if "quota" in low or "zerogpu" in low:
        return ("The free Hugging Face GPU quota for InstantMesh is used up. "
                "Set HF_TOKEN (a free access token) before starting the backend, or try again later.")
    if "out of memory" in low:
        return ("The GPU ran out of memory. Try S2S_LOW_VRAM=1; for Hunyuan lower S2S_HY_OCT (e.g. 192); "
                "for local InstantMesh set S2S_IM_CONFIG=configs/instant-mesh-base.yaml.")
    if any(w in low for w in("connecterror","connection","timeout","name resolution","max retries")):
        return "Could not reach Hugging Face. Check your internet connection (models download on first use)."
    return text[:400]


def _cleanup_old_jobs():
    cutoff=time.time()-JOB_TTL_SECONDS
    for d in OUTPUTS.iterdir():
        if d.is_dir() and d.stat().st_mtime<cutoff:
            shutil.rmtree(d,ignore_errors=True)
    with JOBS_LOCK:
        for jid in[j for j,v in JOBS.items() if v["created"]<cutoff]:
            del JOBS[jid]


def _run_job(job_id,sketch_path,prompt,input_type="",backend="auto",seed=SEED):
    # imported here so Flask starts instantly (rembg/onnxruntime are heavy)
    from base.preprocessing import preprocess_sketch
    from base.background_removal import remove_background

    job_dir=OUTPUTS/job_id
    _update(job_id,status="queued",label="Waiting for the previous job to finish")
    log.info("Job %s | queued, waiting for the GPU lock",job_id)
    while not RUN_LOCK.acquire(timeout=1):
        if cancel.is_set(job_id):   # cancelled while still waiting in the queue
            _update(job_id,status="cancelled",label="Cancelled")
            log.info("Job %s | cancelled while queued",job_id)
            cancel.done(job_id)
            return
    job_handler=logs.attach_job_log(job_id)   # only this thread's records, only while it holds the lock
    started=time.time()
    t=time.time()

    def lap(stage):
        nonlocal t
        now=time.time()
        log.info("Job %s | stage done: %s (%.1fs)",job_id,stage,now-t)
        t=now
        cancel.check(job_id)
    try:
        cancel.check(job_id)
        _update(job_id,status="running",step=1,label="Reading your sketch")
        # the canvas tab is always a drawing; uploads are classified automatically
        force="sketch" if input_type=="draw" else None
        control,kind=preprocess_sketch(sketch_path,job_dir/"control.png",force_kind=force)
        log.info("Job %s | input_type=%s, treated as %s, seed=%d",job_id,input_type or "?",kind,seed)
        lap("preprocessing")
        (job_dir/"job.json").write_text(json.dumps({"prompt":prompt,"kind":kind,"seed":seed}),encoding="utf-8")

        if kind=="photo" and PHOTO_DIRECT:
            # a photo is already a real picture of the object: skip the
            # sketch->image model (it only degrades it) and go to the cutout
            _update(job_id,step=2,label="Photo detected, using it directly")
            rendered=job_dir/"rendered.png"
            from base.preprocessing import load_photo
            load_photo(sketch_path).save(rendered)   # original resolution, no padding
        else:
            loaded=controlnet.status()["loaded"]
            _update(job_id,step=2,label="Rendering the object from your sketch" if loaded
                    else "Loading the image model (first run downloads several GB)")
            rendered=controlnet.sketch_to_image(control,prompt,job_dir/"rendered.png",seed=seed,kind=kind)
        lap("render")
        _update(job_id,preview_url=f"/files/{job_id}/rendered.png")

        _update(job_id,step=3,label="Cutting out the object")
        cutout=remove_background(rendered,job_dir/"foreground.png")
        lap("background removal")

        _update(job_id,step=4,label="Building the 3D mesh")
        controlnet.park()   # free the GPU for the mesh model
        mesh,used,stats=make_mesh(cutout,job_dir,on_stage=lambda text:(log.info("Job %s | %s",job_id,text),_update(job_id,label=text)),choice=backend,seed=seed)
        lap("mesh")

        _update(job_id,label="Checking and tidying the mesh")
        post=clean_mesh(mesh)   # None = skipped or failed, the raw mesh is kept
        stats=post or stats
        lap("validate + clean-up")
        _update(job_id,status="done",label="Done",
                model_url=f"/files/{job_id}/{mesh.name}",
                format=mesh.suffix.lstrip("."),
                backend=used,
                seed=seed,
                mesh_stats=stats,
                filename=f"sketch2shape_{job_id}{mesh.suffix}")
        log.info("Job %s | finished in %.0fs (mesh: %s, %d faces, look: %s)",job_id,time.time()-started,used,stats["faces"],stats["look"])
    except Exception as exc:
        if cancel.is_set(job_id):
            log.info("Job %s | cancelled after %.0fs",job_id,time.time()-started)
            _update(job_id,status="cancelled",label="Cancelled")
        else:
            log.exception("Job %s | failed after %.0fs",job_id,time.time()-started)
            _update(job_id,status="error",error=_friendly(exc))
    finally:
        logs.detach_job_log(job_handler)
        cancel.done(job_id)
        RUN_LOCK.release()


# -- request logging --------------------------------------------------------

QUIET_ROUTES=("/health","/jobs/","/client-log","/files/","/backends")   # polled constantly: only log when they fail


@app.before_request
def _req_start():
    request._t0=time.time()


@app.after_request
def _req_end(resp):
    ms=(time.time()-getattr(request,"_t0",time.time()))*1000
    path=request.path[4:] if request.path.startswith("/api/") else request.path
    quiet=path.startswith(QUIET_ROUTES)
    line=("%s %s -> %d (%.0f ms)",request.method,request.path,resp.status_code,ms)
    if resp.status_code>=500:
        log.error(*line)
    elif resp.status_code>=400:
        log.warning(*line)
    elif quiet:
        log.debug(*line)
    else:
        log.info(*line)
    return resp


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


@bp.get("/backends")
def backends():
    return jsonify({"backends":choices()})


@bp.post("/generate")
def generate():
    upload=request.files.get("image")
    if upload is None or not upload.filename:
        return error_response("No image file provided.",400)

    prompt=(request.form.get("prompt") or "").strip()[:400] or "a clean 3D object"
    input_type=(request.form.get("input_type") or "").strip().lower()
    backend=(request.form.get("backend") or "auto").strip().lower()
    try:
        seed=int((request.form.get("seed") or "").strip() or SEED)
    except ValueError:
        return error_response("Seed must be a whole number.",400)
    if not 0<=seed<=2**31-1:
        return error_response("Seed must be between 0 and 2147483647.",400)
    try:
        resolve(backend)
    except ValueError as exc:
        return error_response(str(exc),400)
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
    log.info("Job %s | prompt=%r | 3D backend=%s | seed=%d",job_id,prompt,backend,seed)
    cancel.new(job_id)
    threading.Thread(target=_run_job,args=(job_id,sketch_path,prompt,input_type,backend,seed),daemon=True).start()
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


@bp.post("/jobs/<job_id>/cancel")
def job_cancel(job_id):
    with JOBS_LOCK:
        job=JOBS.get(job_id)
        status=job["status"] if job else None
    if status is None:
        return error_response("Unknown job. The server may have restarted.",404)
    if status in("done","error","cancelled"):
        return jsonify({"job_id":job_id,"status":status})   # nothing left to stop
    cancel.request(job_id)
    _update(job_id,label="Cancelling...")
    log.info("Job %s | cancel requested",job_id)
    return jsonify({"job_id":job_id,"status":"cancelling"}),202


@bp.post("/client-log")
def client_log_route():
    """Receives batched browser events: {session, events:[{t,level,msg,data}]}. Always 204."""
    body=request.get_json(silent=True,force=True) or {}
    session=str(body.get("session",""))[:12] or "?"
    for ev in(body.get("events") or[])[:100]:
        level=str(ev.get("level","info")).upper()
        level=level if level in("DEBUG","INFO","WARNING","ERROR") else "INFO"
        data=ev.get("data")
        extra=f" | {json.dumps(data,default=str)[:800]}" if data else ""
        client_log.log(getattr(logging,level),"%-7s s=%s %s%s",level,session,str(ev.get("msg",""))[:400],extra)
    return "",204


@bp.get("/files/<job_id>/<path:name>")
def files(job_id,name):
    if not re.fullmatch(r"[0-9a-f]{12}",job_id):
        return error_response("Not found.",404)
    return send_from_directory(OUTPUTS/job_id,name,mimetype=MIME.get(Path(name).suffix.lower()))


app.register_blueprint(bp,url_prefix="/api")
app.register_blueprint(bp,name="api_root")


# -- startup ----------------------------------------------------------------

log.info("Mesh backends, in the order they are tried: %s",", ".join(chain()))
log.info("Logs: %s (backend.log, frontend.log, jobs/<id>.log)",logs.LOG_DIR)

def _preload():
    try:
        controlnet.load()
    except Exception as exc:
        log.warning("Model preload failed, the next job retries it: %s",exc)   # also reported through /health


threading.Thread(target=_preload,daemon=True).start()

if __name__=="__main__":
    # use_reloader=False: the debug reloader would load the models twice
    app.run(host="127.0.0.1",port=8000,debug=False,threaded=True,use_reloader=False)