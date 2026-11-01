"""
logs.py
Separate, rotating log files for the backend and the browser.

  backend/logs/backend.log   everything the Flask server / pipeline does
  backend/logs/frontend.log  events the browser ships to POST /api/client-log
  backend/logs/jobs/<id>.log one file per generation job (full trace of that job)

Env:
  S2S_LOG_LEVEL   DEBUG | INFO (default) | WARNING ...   backend verbosity
  S2S_LOG_DIR     override the log folder
"""

import logging
import logging.handlers
import os
import threading
from pathlib import Path

LOG_DIR=Path(os.getenv("S2S_LOG_DIR") or Path(__file__).resolve().parent.parent/"logs")
JOB_LOG_DIR=LOG_DIR/"jobs"
BACKEND_FMT="%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
FRONTEND_FMT="%(asctime)s %(message)s"
_ready=False


def _rotating(path,fmt):
    h=logging.handlers.RotatingFileHandler(path,maxBytes=5*1024*1024,backupCount=3,encoding="utf-8")
    h.setFormatter(logging.Formatter(fmt))
    return h


def setup():
    """Call once at startup. Safe to call twice."""
    global _ready
    if _ready:
        return
    _ready=True
    LOG_DIR.mkdir(parents=True,exist_ok=True)
    JOB_LOG_DIR.mkdir(parents=True,exist_ok=True)
    level=getattr(logging,os.getenv("S2S_LOG_LEVEL","INFO").upper(),logging.INFO)

    root=logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    console=logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [BE] %(message)s"))
    root.addHandler(console)
    root.addHandler(_rotating(LOG_DIR/"backend.log",BACKEND_FMT))

    # browser events: own file + own console prefix, never mixed into backend.log
    client=logging.getLogger("sketch2shape.client")
    client.setLevel(logging.DEBUG)
    client.propagate=False
    fe_console=logging.StreamHandler()
    fe_console.setFormatter(logging.Formatter("%(asctime)s [FE] %(message)s"))
    client.addHandler(fe_console)
    client.addHandler(_rotating(LOG_DIR/"frontend.log",FRONTEND_FMT))

    # Flask's own access line would duplicate our request log
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def attach_job_log(job_id):
    """Adds backend/logs/jobs/<id>.log to the root logger. Returns a handler to pass to detach_job_log."""
    h=logging.FileHandler(JOB_LOG_DIR/f"{job_id}.log",encoding="utf-8")
    h.setFormatter(logging.Formatter(BACKEND_FMT))
    me=threading.get_ident()
    h.addFilter(lambda record:record.thread==me)   # other requests' lines stay out of this job's file
    logging.getLogger().addHandler(h)
    return h


def detach_job_log(handler):
    logging.getLogger().removeHandler(handler)
    handler.close()
