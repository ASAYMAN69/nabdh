"""Same-origin FastAPI entrypoint serving the API and static frontend."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from nabdh import __version__

STATIC_DIR = Path(__file__).resolve().parent / "static"

# The app is same-origin. The only third-party origins used are Google Fonts
# (stylesheet + font binaries). Inline styles are required because the queue
# renderer writes ``style="..."`` attributes; scripts are external only.
_APP_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Swagger UI and ReDoc load their assets from a CDN, so they keep a relaxed
# policy rather than being broken by the app's strict CSP.
_DOCS_PREFIXES = ("/docs", "/redoc")

app = FastAPI(
    title="Nabdh",
    description="Precision Prevention & Screening Population Triage Engine",
    version=__version__,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline browser-hardening headers to every response."""
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if not request.url.path.startswith(_DOCS_PREFIXES):
        response.headers.setdefault("Content-Security-Policy", _APP_CSP)
    # Demo/dev: never let a stale app.js or stylesheet mask a fresh deploy.
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample" / "clinician_template.csv"
MINIMAL_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "sample" / "clinician_template_minimal.csv"
)
LAB_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "sample" / "clinician_template_lab_units.csv"
)


@app.api_route("/clinician_template.csv", methods=["GET", "HEAD"], include_in_schema=False)
def clinician_template() -> FileResponse:
    """Serve the full clinician CSV template as a download."""
    return FileResponse(
        TEMPLATE_PATH,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="nabdh_clinician_template.csv"',
            "Cache-Control": "no-cache",
        },
    )


@app.api_route(
    "/clinician_template_minimal.csv", methods=["GET", "HEAD"], include_in_schema=False
)
def clinician_template_minimal() -> FileResponse:
    """Serve the starter template (id, age, sex, pregnant) as a download."""
    return FileResponse(
        MINIMAL_TEMPLATE_PATH,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="nabdh_clinician_template_minimal.csv"',
            "Cache-Control": "no-cache",
        },
    )


@app.api_route(
    "/clinician_template_lab_units.csv", methods=["GET", "HEAD"], include_in_schema=False
)
def clinician_template_lab_units() -> FileResponse:
    """Serve the template with non-standard lab units in the column names."""
    return FileResponse(
        LAB_TEMPLATE_PATH,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="nabdh_clinician_template_lab_units.csv"',
            "Cache-Control": "no-cache",
        },
    )


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def serve_index() -> FileResponse:
    """Serve the vanilla HTML/JS/CSS frontend on the same origin."""
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.api_route("/guide", methods=["GET", "HEAD"], include_in_schema=False)
def serve_guide() -> FileResponse:
    """Serve the clinician and developer data guide."""
    return FileResponse(
        STATIC_DIR / "guide.html",
        headers={"Cache-Control": "no-cache"},
    )
