from django.contrib.gis.db import models


class PriceImport(models.Model):
    """One imported price file. The hash makes imports idempotent and versions the plan cache."""

    file_sha256 = models.CharField(max_length=64, unique=True)
    file_name = models.CharField(max_length=255)
    imported_at = models.DateTimeField(auto_now_add=True)
    rows_total = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    rows_non_us = models.PositiveIntegerField(default=0)
    rows_invalid = models.PositiveIntegerField(default=0)
    stations_total = models.PositiveIntegerField(default=0)
    stations_exit = models.PositiveIntegerField(default=0)
    stations_city = models.PositiveIntegerField(default=0)
    stations_unlocated = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.file_name} ({self.file_sha256[:12]})"


class FuelStation(models.Model):
    class LocationSource(models.TextChoices):
        EXIT = "EXIT", "Highway exit"
        CITY = "CITY", "City centroid"
        NONE = "NONE", "Not located"

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField(null=True)
    location = models.PointField(geography=True, srid=4326, null=True)
    # Projected copy (Albers CONUS, meters) for fast, accurate corridor math. GiST-indexed.
    location_5070 = models.PointField(srid=5070, null=True)
    location_source = models.CharField(
        max_length=4, choices=LocationSource, default=LocationSource.NONE
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.opis_id})"


class FuelPrice(models.Model):
    """Raw price observation; duplicates are kept (DESIGN.md §2)."""

    station = models.ForeignKey(FuelStation, on_delete=models.CASCADE, related_name="prices")
    price_import = models.ForeignKey(PriceImport, on_delete=models.CASCADE, related_name="prices")
    # Source values carry up to 8 decimals (e.g. 3.00733333); store them unrounded.
    price = models.DecimalField(max_digits=10, decimal_places=8)


class StationEffectivePrice(models.Model):
    """Read-only view over the materialized view built in migration 0002."""

    station = models.OneToOneField(
        FuelStation, primary_key=True, on_delete=models.DO_NOTHING, db_column="station_id"
    )
    min_price = models.DecimalField(max_digits=10, decimal_places=8)
    avg_price = models.DecimalField(max_digits=10, decimal_places=8)
    n_obs = models.PositiveIntegerField()

    class Meta:
        managed = False
        db_table = "station_effective_price"
