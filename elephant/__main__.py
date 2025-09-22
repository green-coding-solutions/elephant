"""Entry point for the Elephant service."""

import argparse
import uvicorn


def main() -> None:
    """Run the Elephant service."""
    parser = argparse.ArgumentParser(description="Elephant Carbon Grid Intensity Service")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()

    uvicorn.run(
        "elephant.app:app",
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()
