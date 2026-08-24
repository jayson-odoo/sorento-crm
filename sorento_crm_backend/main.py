"""FastAPI application entry point - redirect to app.main.

Run modes:
  - `python main.py`            - reads API_HOST / API_PORT from .env via Settings.
  - `uvicorn main:app --reload` - uvicorn CLI ignores .env, falls back to port 8000.
                                  Use `./run.sh` or pass `--port $API_PORT` instead.
"""
from app.main import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn
    from app.config import settings

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
