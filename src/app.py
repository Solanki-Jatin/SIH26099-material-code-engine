from fastapi import FastAPI

from .persistence import init_db
from .persistence.routes import router as persistence_router
from .review_api.routes import router as review_router


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


@app.get("/")
def root():
    return {
        "project": "SIH26099 Material Code Engine",
        "status": "running",
    }