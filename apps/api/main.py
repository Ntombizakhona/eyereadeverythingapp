from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.jobs import router as jobs_router
from routes.uploads import router as uploads_router
from routes.voice_profiles import router as voice_profiles_router

app = FastAPI(
    title="eyereadeverything API",
    description="Blog-to-Video & Talk-to-Video platform powered by Amazon Nova",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
app.include_router(uploads_router, prefix="/uploads", tags=["Uploads"])
app.include_router(voice_profiles_router, prefix="/voice-profiles", tags=["Voice Profiles"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "eyereadeverything-api"}


# AWS Lambda entrypoint (via API Gateway / Lambda Function URL).
# `mangum` adapts the ASGI app to the Lambda handler interface.
# Running locally with uvicorn ignores this; Lambda invokes `main.handler`.
try:
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:  # mangum not installed in some local environments
    handler = None

