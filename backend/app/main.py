
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_analyses, routes_misc
from .config import Settings, get_settings
from .db.session import make_engine, make_session_factory
from .errors import register_error_handlers
from .logging_config import configure_logging
from .middleware import BodyLimitMiddleware, RequestContextMiddleware
from .ratelimit import DatabaseRateLimiter, RateLimiter
from .services.company import NoCompanySearchProvider
from .services.listings import AdzunaListingProvider
from .services.ml import MlService
from .services.pipeline import Detector
from .services.salary_benchmark import AdzunaSalaryBenchmarks


def create_app(settings: Settings | None = None, detector: Detector | None = None, engine=None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(title="JobSentinel API", version="1.0.0",
                  description="Job-posting risk analysis. Results are heuristic aids, not proof of fraud.")
    app.state.settings = settings
    app.state.engine = engine or make_engine(settings)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.detector = detector or Detector(ml=MlService.from_settings(settings), registry=NoCompanySearchProvider(),
                                                      listings=AdzunaListingProvider(settings),
                                                      salary_benchmarks=AdzunaSalaryBenchmarks(settings))
    app.state.limiter = (DatabaseRateLimiter(app.state.session_factory, settings.rate_limit_per_minute) if settings.rate_limit_backend == "database"
                         else RateLimiter(settings.rate_limit_per_minute))

    if settings.is_production and "*" in settings.cors_origin_list:
        raise RuntimeError("CORS_ORIGINS must list explicit origins in production.")
    # innermost first: CORS handles preflight, then body limit, then request context (outermost)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Session-Token"], expose_headers=["X-Request-ID"], allow_credentials=False)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_upload_bytes + 64 * 1024)
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
    register_error_handlers(app)
    app.include_router(routes_misc.router)
    app.include_router(routes_analyses.router)
    return app
