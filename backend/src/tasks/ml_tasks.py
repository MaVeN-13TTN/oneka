"""
Celery ML scoring tasks — Phase 4.

Tasks:
  score_project_risk_task(project_uuid)
      Called automatically by the satellite pipeline after analysis completes.
      Runs RiskScoringService; falls back gracefully when model is not yet
      trained (returns current divergence-based risk_level instead).

  batch_score_task()
      Weekly re-scoring of all ONGOING projects.
      Registered in the Celery beat schedule (see celery_app.py).
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.celery_app import celery_app
from src.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.tasks.ml_tasks.score_project_risk_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def score_project_risk_task(self, project_uuid: str) -> dict:
    """
    Score a single project with the ML model and persist results to DB.

    Args:
        project_uuid: String UUID of the project to score.

    Returns:
        Dict: {project_uuid, ghost_probability, risk_level,
               model_version, model_available}.
    """
    from src.services.risk_scoring_service import RiskScoringService

    db = SessionLocal()
    try:
        svc = RiskScoringService()
        result = svc.score_project(UUID(project_uuid), db)
        output = {
            "project_uuid": project_uuid,
            "ghost_probability": result.ghost_probability,
            "risk_level": result.risk_level,
            "model_version": result.model_version,
            "model_available": result.model_available,
        }
        logger.info("score_project_risk_task complete: %s", output)
        return output
    except LookupError as exc:
        logger.warning("score_project_risk_task: %s", exc)
        return {"project_uuid": project_uuid, "error": str(exc)}
    except (FileNotFoundError, RuntimeError) as exc:
        # Model not trained yet or ML deps missing — return graceful fallback
        logger.warning("score_project_risk_task model unavailable for %s: %s", project_uuid, exc)
        return {
            "project_uuid": project_uuid,
            "ghost_probability": None,
            "risk_level": None,
            "model_version": "not_trained",
            "model_available": False,
        }
    except Exception as exc:
        logger.exception("score_project_risk_task failed for %s", project_uuid)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="src.tasks.ml_tasks.batch_score_task",
    bind=True,
)
def batch_score_task(self) -> dict:
    """
    Batch re-score all ONGOING projects.

    Registered in Celery beat as a weekly task (Sunday 04:00 EAT).

    Returns:
        Dict: {total_projects, scored, fallback}.
    """
    from src.services.risk_scoring_service import RiskScoringService

    db = SessionLocal()
    try:
        svc = RiskScoringService()
        results = svc.score_all_active_projects(db)
        scored = sum(1 for r in results if r.model_available)
        output = {
            "total_projects": len(results),
            "scored": scored,
            "fallback": len(results) - scored,
        }
        logger.info("batch_score_task complete: %s", output)
        return output
    except Exception as exc:
        logger.exception("batch_score_task failed")
        raise
    finally:
        db.close()
