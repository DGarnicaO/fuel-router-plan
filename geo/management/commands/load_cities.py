from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from geo.gazetteer import build_places, read_gazetteer
from geo.models import City


class Command(BaseCommand):
    help = "Load the US Census Gazetteer places file into the City table (replaces existing rows)."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, path: Path, **options):
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        places = build_places(read_gazetteer(path))
        with transaction.atomic():
            City.objects.all().delete()
            City.objects.bulk_create(
                (
                    City(
                        name=p.name,
                        name_norm=p.name_norm,
                        state=p.state,
                        location=Point(p.lon, p.lat, srid=4326),
                    )
                    for p in places
                ),
                batch_size=5000,
            )
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(places)} places"))
