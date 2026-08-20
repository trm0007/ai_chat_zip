from django.core.management.base import BaseCommand

from ai_chat import services


class Command(BaseCommand):
    help = (
        "Scan ai_chat/source/ and sync the search index with what's on disk. "
        "Run this after an admin manually adds, replaces, or removes files "
        "in that folder (including tab1.md-tab4.md). New/changed files are "
        "extracted, chunked, and embedded; removed files are dropped from "
        "the index; unchanged files are skipped."
    )

    def handle(self, *args, **options):
        self.stdout.write(f'Scanning {services.SOURCE_DIR} ...')
        if not services.SOURCE_DIR.is_dir():
            self.stdout.write(self.style.WARNING(
                f'{services.SOURCE_DIR} does not exist yet — create it and add files first.'
            ))
            return

        result = services.index_sources()

        for path in result['added']:
            self.stdout.write(self.style.SUCCESS(f'  + added     {path}'))
        for path in result['updated']:
            self.stdout.write(self.style.SUCCESS(f'  ~ updated   {path}'))
        for path in result['skipped']:
            self.stdout.write(f'  = unchanged {path}')
        for path in result['removed']:
            self.stdout.write(self.style.WARNING(f'  - removed   {path}'))
        for path, error in result['errors']:
            self.stdout.write(self.style.ERROR(f'  ! error     {path}: {error}'))

        self.stdout.write(
            f"Done. {len(result['added'])} added, {len(result['updated'])} updated, "
            f"{len(result['skipped'])} unchanged, {len(result['removed'])} removed, "
            f"{len(result['errors'])} errors."
        )
