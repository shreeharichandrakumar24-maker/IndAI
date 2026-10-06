from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.router import api_router
from backend.core.auth_middleware import AuthMiddleware
from backend.db.scoping import resolve_factory_scope

app = FastAPI(title="IndAI Backend API", description="API for Industrial Administration Platform")

app.add_middleware(AuthMiddleware)

# Register the Session-based factory scoping (X-Factory-Id -> session.info).
# Importing it here guarantees the ORM event listeners are installed at
# startup. Without the header every query behaves exactly as before.
import backend.db.scoping  # noqa: E402,F401

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api", dependencies=[Depends(resolve_factory_scope)])

@app.get("/")
async def root():
    return {"message": "Welcome to the IndAI API. See /docs for documentation."}
