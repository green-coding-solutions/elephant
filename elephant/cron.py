import argparse
import logging
import signal
from threading import Event

from elephant.database import db_connection
from elephant.config import config
from elephant.providers.helpers import get_providers
from elephant.providers.base import CarbonIntensityProvider

logging.basicConfig(level=config.logging.level)
logger = logging.getLogger(__name__)

shutdown_event = Event()


def _request_shutdown(signum, _) -> None:
    """Signal handler to request a graceful shutdown."""
    logger.info("Received signal %s. Shutting down after current iteration.", signum)
    shutdown_event.set()


def wait_with_signal_check(total_seconds: int) -> bool:
    """Wait in 1s increments, returning True if a shutdown signal arrives."""
    for _ in range(total_seconds):
        if shutdown_event.wait(timeout=1):
            return True
    return shutdown_event.is_set()


def run_cron(region=None) -> None:
    """Run a single cron iteration."""
    providers: dict[str, CarbonIntensityProvider] = get_providers()

    with db_connection() as conn, conn.cursor() as cur:
        for source in config.cron.sources:
            region = source.region.upper()
            provider_name = source.provider.lower()
            provider_db_name = f"{source.provider.lower()}_{region.lower()}"

            if region and region != source.region.upper():
                continue

            if provider_name not in providers:
                logger.warning("Provider '%s' for region '%s' is not configured or enabled.", provider_name, region)
                continue

            provider = providers[provider_name]

            logger.debug("Fetching data for '%s' from '%s'.", region, provider_name)

            # We have the update logic here and not in the provider as I
            # want to keep providers decoupled and focused on data retrieval only.
            data = provider.get_historical(region)
            for d in data:
                cur.execute(
                    """
                    INSERT INTO carbon (time, region, carbon_intensity, provider)
                    SELECT %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM carbon
                        WHERE time = %s
                          AND region = %s
                          AND provider = %s
                    );
                    """,
                    (
                        d["time"],
                        d["region"],
                        d.get("carbon_intensity"),
                        provider_db_name,
                        d["time"],
                        d["region"],
                        provider_db_name,
                    ),
                )

            conn.commit()

            logger.info("Successfully saved data for '%s' from '%s'.", region, provider_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Elephant cron job.")
    parser.add_argument(
        "--service",
        action="store_true",
        help="Run continuously in the background (default is one-shot).",
    )
    args = parser.parse_args()

    if not args.service:
        run_cron()
    else:
        signal.signal(signal.SIGINT, _request_shutdown)
        signal.signal(signal.SIGTERM, _request_shutdown)

        while not shutdown_event.is_set():
            run_cron()
            if wait_with_signal_check(config.cron.interval_seconds):
                break
