from django.contrib.gis.db import models


class City(models.Model):
    """US Census Gazetteer place (public domain): request geocoding and station locations."""

    name = models.CharField(max_length=120)
    name_norm = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    location = models.PointField(geography=True, srid=4326)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["state", "name_norm"], name="city_state_name_norm_uniq")
        ]
        verbose_name_plural = "cities"

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"
