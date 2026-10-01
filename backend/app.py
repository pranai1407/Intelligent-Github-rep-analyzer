
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.services.repository_service import RepositoryService


app = FastAPI(
    title="GitHub Repository Analyzer API",
    description="Analyze GitHub repositories and generate reports.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = RepositoryService()

# In-memory job tracking is suitable for a single-process development API.
# For multi-worker production deployments, use shared storage such as Redis.
MAX_PROGRESS_JOBS = 100
progress_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
progress_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_job(job_id: str, data: dict[str, Any]) -> None:
    """Store a job and evict the oldest records when the limit is reached."""
    with progress_lock:
        progress_jobs[job_id] = data
        progress_jobs.move_to_end(job_id)

        while len(progress_jobs) > MAX_PROGRESS_JOBS:
            progress_jobs.popitem(last=False)


def _get_job(job_id: str):
    """Return a shallow copy of a job record."""
    with progress_lock:
        job = progress_jobs.get(job_id)
        return dict(job) if job else None


def _update_job_progress(
    job_id: str,
    *,
    stage: str,
    message: str,
    percent: int,
) -> None:
    """Update progress from the repository service/parser callback."""
    with progress_lock:
        job = progress_jobs.get(job_id)
        if job is None:
            return

        job.update({
            "status": "running",
            "stage": stage,
            "message": message,
            "percent": max(0, min(100, int(percent))),
            "updated_at": _utc_now(),
        })


def _run_analysis_job(job_id: str, repo_url: str) -> None:
    """Run repository analysis in a background thread and store its result."""
    try:
        result = service.analyze_repository(
            repo_url,
            progress_callback=lambda **update: _update_job_progress(
                job_id,
                **update,
            ),
        )

        if isinstance(result, dict) and result.get("status") == "error":
            error_message = result.get(
                "message",
                "Repository analysis failed.",
            )

            with progress_lock:
                job = progress_jobs.get(job_id)
                if job is not None:
                    job.update({
                        "status": "failed",
                        "stage": "failed",
                        "message": error_message,
                        "percent": job.get("percent", 0),
                        "error": error_message,
                        "updated_at": _utc_now(),
                    })
            return

        with progress_lock:
            job = progress_jobs.get(job_id)
            if job is not None:
                job.update({
                    "status": "completed",
                    "stage": "complete",
                    "message": "Repository analysis completed successfully.",
                    "percent": 100,
                    "result": result,
                    "updated_at": _utc_now(),
                })

    except Exception as exc:
        with progress_lock:
            job = progress_jobs.get(job_id)
            if job is not None:
                job.update({
                    "status": "failed",
                    "stage": "failed",
                    "message": f"Repository analysis failed: {exc}",
                    "error": str(exc),
                    "updated_at": _utc_now(),
                })


@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "message": "GitHub Repository Analyzer API is running.",
    }


@app.post("/analyze")
def analyze_repository(repo_url: str):
    """Legacy synchronous analysis endpoint."""
    result = service.analyze_repository(repo_url)

    if isinstance(result, dict) and result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    return result


@app.post("/analyze-progress")
def start_progress_analysis(repo_url: str):
    """Start background analysis and return its job ID."""
    if not service.validate_repository_url(repo_url):
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid GitHub repository URL.",
        )

    job_id = str(uuid.uuid4())
    now = _utc_now()

    _save_job(job_id, {
        "job_id": job_id,
        "repo_url": repo_url.strip(),
        "status": "queued",
        "stage": "queued",
        "message": "Analysis is queued and preparing to start...",
        "percent": 0,
        "created_at": now,
        "updated_at": now,
        "result": None,
    })

    worker = threading.Thread(
        target=_run_analysis_job,
        args=(job_id, repo_url.strip()),
        daemon=True,
        name=f"repository-analysis-{job_id[:8]}",
    )
    worker.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Repository analysis has started.",
        "progress_url": f"/analysis-progress/{job_id}",
    }


@app.get("/analysis-progress/{job_id}")
def get_analysis_progress(job_id: str):
    """Return job status, progress, and final result when available."""
    job = _get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis job not found or no longer available.",
        )

    # Never expose the original repository URL in this response.
    job.pop("repo_url", None)

    return job


@app.post("/ask")
def ask_question(repo_url: str, question: str):
    """Answer a question about a repository."""
    result = service.ask_question(repo_url, question)

    if isinstance(result, dict) and result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    return result


@app.post("/generate-report")
def generate_report(repo_url: str):
    """Generate a PDF report using cached analysis when available."""
    try:
        filename = service.generate_pdf_report(repo_url)
        report_path = Path(filename).resolve()

        if not report_path.is_file():
            raise HTTPException(
                status_code=500,
                detail="The PDF report was not created.",
            )

        return FileResponse(
            path=str(report_path),
            media_type="application/pdf",
            filename="Repository_Analysis_Report.pdf",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to generate the PDF report: {exc}",
        ) from exc