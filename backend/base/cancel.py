"""
cancel.py
Lets the API stop a running job: a flag that the pipeline checks between
stages, plus the engine subprocesses (Hunyuan / local InstantMesh), which are
terminated so the GPU is freed straight away.
"""
import threading

FLAGS={}
PROCS={}
LOCK=threading.Lock()


class Cancelled(Exception):
    pass


def new(job_id):
    with LOCK:
        FLAGS[job_id]=threading.Event()


def is_set(job_id):
    ev=FLAGS.get(job_id)
    return ev is not None and ev.is_set()


def check(job_id):
    if is_set(job_id):
        raise Cancelled("Cancelled by the user.")


def track(job_id,proc):
    """Engines register their subprocess here (the job id is the job folder name)."""
    with LOCK:
        PROCS.setdefault(job_id,[]).append(proc)
    if is_set(job_id):
        proc.terminate()


def request(job_id):
    """Flag the job and kill its engine process. False when the job is not running."""
    with LOCK:
        ev=FLAGS.get(job_id)
        procs=list(PROCS.get(job_id,[]))
    if ev is None:
        return False
    ev.set()
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    return True


def done(job_id):
    with LOCK:
        FLAGS.pop(job_id,None)
        PROCS.pop(job_id,None)