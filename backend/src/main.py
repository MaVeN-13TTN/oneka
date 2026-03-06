"""
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.config import settings
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.rate_limit import limiter
from src.routers import health, procurement, projects, financial, geolocation, satellite, risk, maps, certificates

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Kenya's First Autonomous Infrastructure Auditing Platform - Backend API",
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "https://oneka.ai",  # Production frontend
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    API root endpoint with welcome message and documentation links.
    """
    return {
        "message": "Welcome to ONEKA AI API",
        "description": "Infrastructure Auditing Platform for Ghost Project Detection",
        "version": settings.api_version,
        "documentation": {
            "interactive": "/docs",
            "redoc": "/redoc",
            "openapi_schema": "/openapi.json",
        },
        "health_check": "/api/v1/health",
        "system_status": "/api/v1/status",
    }


# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(procurement.router, prefix="/api/v1", tags=["Procurement"])
app.include_router(projects.router, prefix="/api/v1", tags=["Projects"])
app.include_router(financial.router, prefix="/api/v1", tags=["Financial"])
app.include_router(geolocation.router, prefix="/api/v1", tags=["Geolocation"])
app.include_router(satellite.router, prefix="/api/v1", tags=["Satellite"])
app.include_router(risk.router, prefix="/api/v1", tags=["Risk Scoring"])
app.include_router(maps.router, prefix="/api/v1", tags=["Maps"])
app.include_router(certificates.router, prefix="/api/v1", tags=["Certificates"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unhandled errors.
    """
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
            "path": str(request.url),
        },
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """
    Execute on application startup.
    """
    print(f"🚀 Starting {settings.app_name} v{settings.api_version}")
    print(f"📍 Environment: {settings.environment}")
    print(f"🌐 API Documentation: http://{settings.api_host}:{settings.api_port}/docs")

    # Check database connection
    from src.database import check_db_connection

    if check_db_connection():
        print("✅ Database connection successful")
    else:
        print("❌ Database connection failed - check your DATABASE_URL in .env")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """
    Execute on application shutdown.
    """
    print(f"🛑 Shutting down {settings.app_name}")


# For running with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
