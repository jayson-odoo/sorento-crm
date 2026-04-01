"""Run MCP server (streamable HTTP)."""
from __future__ import annotations

import asyncio
import logging
import sys

from sorento_crm_mcp.server import create_mcp_app
from sorento_crm_mcp.settings import Settings


def main() -> None:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as e:
        print("Configuration error:", e, file=sys.stderr)
        print("Set CRM_BASE_URL and EXTERNAL_API_KEY (see README).", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    mcp = create_mcp_app(settings)
    asyncio.run(mcp.run_streamable_http_async())


if __name__ == "__main__":
    main()
