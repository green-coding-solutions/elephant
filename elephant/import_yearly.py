"""Import bundled yearly Electricity Maps values into the database."""

import argparse
import logging
from pathlib import Path

from elephant.database import db_connection, init_db
from elephant.yearly_dataset import YEARLY_DATA_DIR, YEARLY_PROVIDER, iter_yearly_dataset_records


logger = logging.getLogger(__name__)


def import_yearly_data(data_dir: Path = YEARLY_DATA_DIR) -> int:
    """Import bundled yearly data files into the yearly fallback table."""
    records = list(iter_yearly_dataset_records(data_dir))
    if not records:
        logger.warning("No yearly dataset records found in %s", data_dir)
        return 0

    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM carbon_yearly WHERE provider = %s;", (YEARLY_PROVIDER,))
        existing_count = cur.fetchone()[0]
        expected_count = len(records)

        if existing_count >= expected_count:
            logger.info(
                "Yearly dataset already present (%s/%s rows). Skipping import.",
                existing_count,
                expected_count,
            )
            return 0

        cur.executemany(
            """
            INSERT INTO carbon_yearly (
              year,
              region,
              carbon_intensity,
              provider,
              estimation,
              zone_name,
              country_name,
              display_name
            )
            VALUES (%(year)s, %(region)s, %(carbon_intensity)s, %(provider)s, %(estimation)s,
                    %(zone_name)s, %(country_name)s, %(display_name)s)
            ON CONFLICT (year, region, provider)
            DO NOTHING;
            """,
            records,
        )

        cur.execute("SELECT COUNT(*) FROM carbon_yearly WHERE provider = %s;", (YEARLY_PROVIDER,))
        imported_count = cur.fetchone()[0] - existing_count
        conn.commit()

    logger.info("Imported %s missing yearly dataset rows from %s", imported_count, data_dir)
    return imported_count


def main() -> None:
    """Run the yearly importer."""
    parser = argparse.ArgumentParser(description="Import bundled yearly Electricity Maps data.")
    parser.add_argument("--data-dir", type=Path, default=YEARLY_DATA_DIR, help="Directory containing yearly_*.js files")
    args = parser.parse_args()

    init_db()
    import_yearly_data(args.data_dir)


if __name__ == "__main__":
    main()
