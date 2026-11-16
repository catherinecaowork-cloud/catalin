"""聚合各域 router。"""
from __future__ import annotations

from fastapi import APIRouter

from autotest_control.api import (
    ai,
    auth,
    environments,
    flows,
    objects,
    onboarding,
    recordings,
    runs,
    sites,
    suites,
    workers,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(sites.router)
router.include_router(environments.router)
router.include_router(objects.router)
router.include_router(ai.router)
router.include_router(flows.router)
router.include_router(suites.router)
router.include_router(runs.router)
router.include_router(onboarding.router)
router.include_router(recordings.router)
router.include_router(workers.router)
