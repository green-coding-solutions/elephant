CREATE TABLE IF NOT EXISTS carbon_yearly (
  year              INTEGER           NOT NULL,
  region            TEXT              NOT NULL,
  carbon_intensity  DOUBLE PRECISION  NOT NULL,
  provider          TEXT              NOT NULL,
  estimation        BOOLEAN           NOT NULL DEFAULT TRUE,
  zone_name         TEXT              NULL,
  country_name      TEXT              NULL,
  display_name      TEXT              NULL,
  PRIMARY KEY (year, region, provider)
);

CREATE INDEX IF NOT EXISTS idx_carbon_yearly_region_year
  ON carbon_yearly (region, year);
