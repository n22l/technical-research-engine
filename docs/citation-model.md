# Citation model

Source identity combines URL and raw-content SHA-256; raw capture hash and retrieval timestamp remain auditable. Same-host canonical URLs are hints and cannot transfer authority to other publishers.

HTML preserves title, recognized publication metadata, language, headings and paragraph/list blocks. Scripts/styles/templates are excluded. Exact passage means extracted text (entities decoded and outer whitespace trimmed), not raw HTML. Paragraph numbers are extracted-document locators; offsets refer to joined extracted text.

PDF uses optional pypdf with one-based physical PDF pages. Printed page numbers/headings are not invented; image-only PDFs fail without OCR. Original-language passages remain authoritative even when translations are supplied.

Validation requires an existing claim, allowed parsed source, matching location/source IDs, an actual parsed paragraph and identical text at the stated offsets. Missing metadata stays null; invalid citations are omitted and flagged. Semantic relevance depends on separate hash-bound human review, not automated entailment.

Markdown reports source title/publisher/date, stance and page/section/extracted paragraph with a URL, avoiding long quotations. Exact passages stay private JSON. Synthetic URLs are invented and not expected to resolve.
