from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .persistence import init_db
from .persistence.routes import router as persistence_router
from .review_api.routes import router as review_router
from .dashboard.routes import router as dashboard_router


app = FastAPI(
    title="SIH26099 Material Code Engine",
    version="1.0.0",
)


@app.on_event("startup")
def startup():
    init_db()


# Tier 4: Persistence APIs
app.include_router(persistence_router)

# Tier 3: Human Review APIs
app.include_router(review_router)

# Tier 5: Analytics Dashboard APIs
app.include_router(dashboard_router)


# Serve the two frontend UIs directly from this same app
_root = Path(__file__).resolve().parent
app.mount("/review-ui", StaticFiles(directory=str(_root / "review_api" / "static")), name="review-ui")
app.mount("/dashboard-ui", StaticFiles(directory=str(_root / "dashboard" / "static")), name="dashboard-ui")


@app.get("/")
def root():
    return {
        "project": "SIH26099 Material Code Engine",
        "status": "running",
        "review_ui": "/review-ui/index.html",
        "dashboard_ui": "/dashboard-ui/index.html",
    }
