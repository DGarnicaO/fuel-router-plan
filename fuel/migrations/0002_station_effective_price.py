from django.db import migrations

# Effective price per station from the most recent import. The unique index on station_id is
# what allows REFRESH MATERIALIZED VIEW CONCURRENTLY (readers are never blocked).
CREATE_VIEW = """
CREATE MATERIALIZED VIEW station_effective_price AS
SELECT
    p.station_id,
    MIN(p.price) AS min_price,
    AVG(p.price) AS avg_price,
    COUNT(*) AS n_obs
FROM fuel_fuelprice p
WHERE p.price_import_id = (SELECT MAX(id) FROM fuel_priceimport)
GROUP BY p.station_id;

CREATE UNIQUE INDEX station_effective_price_station_id_uniq
    ON station_effective_price (station_id);
"""

DROP_VIEW = "DROP MATERIALIZED VIEW IF EXISTS station_effective_price;"


class Migration(migrations.Migration):
    dependencies = [("fuel", "0001_initial")]

    operations = [migrations.RunSQL(CREATE_VIEW, reverse_sql=DROP_VIEW)]
