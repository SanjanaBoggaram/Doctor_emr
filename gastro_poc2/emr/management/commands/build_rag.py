"""
(Re)build the RAG index from everything in rag_data/.

    python manage.py build_rag

Run this whenever you add or change files in rag_data/.
"""

from django.core.management.base import BaseCommand

from core import rag


class Command(BaseCommand):
    help = "Build the Chroma vector index from documents in rag_data/."

    def handle(self, *args, **opts):
        files = rag.iter_source_files()
        if not files:
            self.stdout.write(self.style.WARNING(
                f"No documents found in {rag.RAG_DATA_DIR} "
                f"(supported: {', '.join(sorted(rag.SUPPORTED_EXTS))})."
            ))
            return

        self.stdout.write(f"Indexing {len(files)} file(s) from {rag.RAG_DATA_DIR} ...")
        stats = rag.build_index(verbose=True)
        self.stdout.write(self.style.SUCCESS(
            f"Done. {stats['files']} file(s) -> {stats['chunks']} chunks "
            f"in {rag.RAG_STORE_DIR}."
        ))
        if not rag.rag_enabled():
            self.stdout.write(self.style.WARNING(
                "Note: RAG_ENABLED is not set to true in .env, so the chat "
                "won't use this index until you enable it."
            ))
