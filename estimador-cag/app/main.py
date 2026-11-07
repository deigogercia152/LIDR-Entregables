from fastapi import FastAPI

from app.routers.estimations import router as estimations_router
from app.routers.sessions import router as sessions_router

app = FastAPI(
    title="Estimador CAG",
    description="API para generar estimaciones de proyectos de software a partir de transcripciones de reuniones.",
)

app.include_router(estimations_router, prefix="/api/v1", tags=["estimations"])
app.include_router(sessions_router, prefix="/api/v1", tags=["sessions"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
