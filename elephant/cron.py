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


def run_cron(specific_region=None, specific_provider=None) -> None:
    """Run a single cron iteration."""
    providers: dict[str, CarbonIntensityProvider] = get_providers()

    with db_connection() as conn, conn.cursor() as cur:
        for source in config.cron.sources:
            region = source.region.upper()
            provider_name = source.provider.lower()
            provider_db_name = f"{source.provider.lower()}_{source.region.lower()}"

            if specific_region and specific_region.upper() != region:
                logger.debug("Skipping region '%s' as specific_region is set to '%s'.", region, specific_region)
                continue

            if specific_provider and specific_provider.lower() != provider_name:
                logger.debug("Skipping provider '%s' as specific_provider is set to '%s'.", provider_name, specific_provider)
                continue

            if provider_db_name not in providers:
                logger.warning("Provider '%s' for region '%s' is not configured or enabled.", provider_db_name, region)
                continue


            provider = providers[provider_db_name]

            logger.debug("Fetching data for '%s' from '%s'.", region, provider_db_name)

            # We have the update logic here and not in the provider as I
            # want to keep providers decoupled and focused on data retrieval only.
            if source.only_get_current:
                past = provider.get_current(region) or []
                future = []
            else:
                past = provider.get_historical(region) or []
                future = provider.get_future(region) or []

            data = past + future # For now we merge the two. This will change in the future when modelling becomes more important

            if not data:
                logger.error("No data returned for '%s' from '%s'.", region, provider_db_name)
                continue

            inserted_count = 0
            for d in data:

                if set(d.keys()) != {"region", "time", "carbon_intensity", "provider", "resolution", "estimation"}:
                    raise ValueError(f"Provider '{provider_db_name}' returned data with invalid keys: {set(d.keys())}")

                cur.execute(
                    """
                    INSERT INTO carbon (time, region, carbon_intensity, provider, estimation)
                    SELECT %s, %s,  %s, %s, %s
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
                        d["estimation"],
                        d["time"],
                        d["region"],
                        provider_db_name,
                    ),
                )
                if cur.rowcount and cur.rowcount > 0:
                    inserted_count += cur.rowcount

            conn.commit()

            logger.info(
                "Successfully received data (%s records, %s inserts) for '%s' from '%s'.",
                len(data),
                inserted_count,
                region,
                provider_db_name,
            )


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
