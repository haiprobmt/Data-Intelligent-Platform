from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Job
from app.services.audit import audit


def create_job(db: Session, tenant_id: str, job_type: str, message: str) -> Job:
    job = Job(tenant_id=tenant_id, job_type=job_type, message=message)
    db.add(job)
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
        job.updated_at = datetime.utcnow()
        db.commit()

        result = task(db, tenant_id, job_id)

        job.status = "completed"
        job.result = result
        job.message = "Completed successfully"
        job.updated_at = datetime.utcnow()
        audit(db, tenant_id, f"{job.job_type}.completed", {"job_id": job_id})
        db.commit()
    except Exception as exc:
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.message = str(exc)
            job.updated_at = datetime.utcnow()
            audit(db, tenant_id, f"{job.job_type}.failed", {"job_id": job_id, "error": str(exc)})
            db.commit()
    finally:
        db.close()
