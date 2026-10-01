from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fuel.importer import import_prices
from geo.models import City


class Command(BaseCommand):
    help = "Import a fuel price CSV (idempotent by file hash) and refresh effective prices."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, path: Path, **options):
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if not City.objects.exists():
            raise CommandError("City table is empty. Run load_cities first.")
        report = import_prices(path)
        for line in report.lines():
            self.stdout.write(line)
