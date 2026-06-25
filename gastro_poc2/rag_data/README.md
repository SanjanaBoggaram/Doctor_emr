# rag_data — clinical reference material for the intake agent

Drop reference documents here, then run:

```bash
python manage.py build_rag
```

**Supported formats:** `.txt`, `.md`, `.pdf` (sub-folders are scanned too).

These documents are chunked, embedded, and stored in `../rag_store/`. At chat
time the intake agent retrieves the most relevant snippets (based on the
patient's recent answers) and uses them to ask better, guideline-grounded
follow-up questions. The reference text is **never** shown verbatim to the
patient.

Good things to put here:
- Gastroenterology symptom-questioning guides / intake checklists
- Red-flag / alarm-feature criteria
- Differential-diagnosis questioning frameworks
- Clinic-specific protocols

The sample file `gastro_intake_guidelines.md` is included so RAG works out of the
box — replace or augment it with your own material.

> Anything you place here is embedded locally by default (no data leaves your
> machine). If you switch `RAG_EMBED_PROVIDER=gemini`, document text and patient
> queries are sent to Google's embedding API instead.
