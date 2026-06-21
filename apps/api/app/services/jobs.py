from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Job, JobLog
from app.services.audit import audit


def create_job(db: Session, tenant_id: str, job_type: str, message: str) -> Job:
    job = Job(tenant_id=tenant_id, job_type=job_type, message=message)
    db.add(job)
    db.flush()
    log_job(db, tenant_id, job.id, "info", message)
    audit(db, tenant_id, f"{job_type}.queued", {"job_id": job.id})
    db.commit()
    db.refresh(job)
    return job


def enqueue_job(
    background_tasks: BackgroundTasks,
    db: Session,
    tenant_id: str,
    job_type: str,
    message: str,
    task: Callable[[Session, str, str], dict[str, Any]],
) -> Job:
    job = create_job(db, tenant_id, job_type, message)
    background_tasks.add_task(run_job, job.id, tenant_id, task)
    return job


def run_job(job_id: str, tenant_id: str, task: Callable[[Session, str, str], dict[str, Any]]) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.tenant_id != tenant_id:
            return
        job.status = "running"
        job.progress_percent = 5
        job.updated_at = datetime.utcnow()
        log_job(db, tenant_id, job.id, "info", "Job started")
        db.commit()

        result = task(db, tenant_id, job_id)

        job.status = "completed"
        job.result = result
        job.message = "Completed successfully"
        job.progress_percent = 100
        job.updated_at = datetime.utcnow()
        log_job(db, tenant_id, job.id, "info", "Job completed")
        audit(db, tenant_id, f"{job.job_type}.completed", {"job_id": job_id})
        db.commit()
    except Exception as exc:
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.message = str(exc)
            job.updated_at = datetime.utcnow()
            log_job(db, tenant_id, job.id, "error", str(exc))
            audit(db, tenant_id, f"{job.job_type}.failed", {"job_id": job_id, "error": str(exc)})
            db.commit()
    finally:
        db.close()


def update_job_progress(db: Session, tenant_id: str, job_id: str, progress_percent: int, message: str | None = None) -> None:
    job = db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id:
        return
    if job.cancel_requested:
        raise RuntimeError("Job cancellation requested")
    job.progress_percent = max(0, min(100, progress_percent))
    if message:
        job.message = message
        log_job(db, tenant_id, job_id, "info", message)
    job.updated_at = datetime.utcnow()
    db.commit()


def request_job_cancel(db: Session, tenant_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise ValueError("Job not found")
    job.cancel_requested = True
    job.message = "Cancellation requested"
    job.updated_at = datetime.utcnow()
    log_job(db, tenant_id, job_id, "warning", "Cancellation requested")
    db.commit()
    db.refresh(job)
    return job


def log_job(db: Session, tenant_id: str, job_id: str, level: str, message: str, details: dict[str, Any] | None = None) -> None:
    db.add(JobLog(tenant_id=tenant_id, job_id=job_id, level=level, message=message, details=details))
