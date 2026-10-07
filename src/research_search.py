"""Offline passage retrieval. No network clients, model downloads, or config discovery."""
import sys

sys.dont_write_bytecode = True

import argparse
from collections import Counter
from datetime import date
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"


class SafeError(Exception):
    """Only fixed, non-sensitive messages may reach the command line."""


def external_directory(value):
    if not value:
        raise SafeError("Private mode requires TECH_RESEARCH_DATA_DIR (or legacy SPACE_DATA_DIR) pointing to an existing external directory.")
    try:
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_dir() or path == ROOT or ROOT in path.parents:
            raise SafeError("Private directory must be outside the public repository.")
        # A .git file also marks linked worktrees and submodules. Inspect all ancestors,
        # including inaccessible/dangling markers, before asking Git about discovery.
        for parent in (path, *path.parents):
            if os.path.lexists(parent / ".git") or (
                (parent / "HEAD").exists() and (parent / "objects").is_dir()
                and (parent / "refs").is_dir()
            ):
                raise SafeError("Private directory must not be inside any Git working tree or bare repository.")
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", LC_ALL="C")
        check = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, env=env, timeout=10,
        )
        if check.returncode != 128 or b"not a git repository" not in check.stderr.lower():
            raise SafeError("Could not establish a non-Git private directory; access denied.")
        return path
    except SafeError:
        raise
    except (OSError, RuntimeError, subprocess.SubprocessError):
        raise SafeError("Private directory validation failed; check directory access and Git installation.") from None


def private_directory():
    """Prefer the generic setting; an invalid explicit value must not fall back."""
    value = os.environ.get("TECH_RESEARCH_DATA_DIR")
    if value is None:
        value = os.environ.get("SPACE_DATA_DIR")
    return external_directory(value)


def safe_file(base, relative):
    """Reject escapes, symlinks/junctions, and alternate file streams."""
    if not isinstance(relative, str) or not relative or ":" in relative:
        raise SafeError("Invalid corpus file reference.")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise SafeError("Corpus files must remain within the configured data directory.")
    candidate = base / part
    for item in (candidate, *candidate.parents):
        if item == base:
            break
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise SafeError("Linked corpus files and directories are not permitted.")
    resolved = candidate.resolve(strict=True)
    if base not in resolved.parents or not resolved.is_file() or resolved.stat().st_nlink != 1:
        raise SafeError("Corpus files must be ordinary files within the data directory.")
    if base != DEMO.resolve():
        external_directory(resolved.parent)
    return resolved


def read_json(base, name):
    return json.loads(safe_file(base, name).read_text(encoding="utf-8"))


def demo_directory():
    for item in (DEMO, DEMO.parent):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise SafeError("Demo directory must not link to external material.")
    path = DEMO.resolve(strict=True)
    if ROOT not in path.parents:
        raise SafeError("Demo directory must be inside the public project.")
    return path


def load_passages(base):
    records = read_json(base, "documents.json")
    if not isinstance(records, list) or not records:
        raise SafeError("Document manifest must be a nonempty JSON array.")
    passages, seen = [], set()
    for record in records:
        required = ("id", "title", "publisher", "source_url", "publication_date", "language", "file")
        if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k].strip() for k in required):
            raise SafeError("Document metadata is incomplete or invalid.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", record["id"]) or record["id"] in seen:
            raise SafeError("Document IDs must be unique ASCII identifiers.")
        # Metadata syntax is independent of retrieval quality. Only English and
        # Chinese retrieval have fixture coverage; this is not full BCP 47 validation.
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", record["language"]):
            raise SafeError("Document language must be a hyphen-separated language tag.")
        if "domain" in record and (not isinstance(record["domain"], str) or not record["domain"].strip()):
            raise SafeError("Document domain must be a nonempty string when provided.")
        if record["publication_date"] != "unknown":
            date.fromisoformat(record["publication_date"])
        if not record["source_url"].startswith(("https://", "http://", "synthetic:")):
            raise SafeError("Source URL must be HTTP(S), or synthetic: for invented fixtures.")
        seen.add(record["id"])
        text = safe_file(base, record["file"]).read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            raise SafeError("A document contains no text passages.")
        metadata = {k: record[k] for k in required if k != "file"}
        if "domain" in record:
            metadata["domain"] = record["domain"]
        for number, paragraph in enumerate(paragraphs, 1):
            passages.append({"passage_id": f"{record['id']}:p{number}",
                             "passage": paragraph,
                             "source": dict(metadata),
                             "paragraph": number})
    return passages


def tokens(text):
    text = unicodedata.normalize("NFKC", text).lower()
    output = re.findall(r"[a-z0-9]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        output.extend(run)
        output.extend(run[i:i + 2] for i in range(len(run) - 1))
    return Counter(output)


SEARCH_STOP = set("a an the is are was were has have had do does did what when where which who how of to in on at for and or with by from current latest evidence official source confirm contradict verify please tell me about can could would should this that these those it its be been being".split())


def keyword_tokens(text):
    # Preserve token identities used by ingestion; retrieval filtering is separate.
    result = tokens(text)
    for technical in re.findall(r'[A-Za-z]+(?:-[A-Za-z0-9]+)+', text.lower()):
        result[technical] += 1
    from retrieval_constraints import concepts
    for concept in concepts(text):
        result[concept] += 1
    # Small retrieval-only vocabulary, not translation or a capability judgment.
    aliases = {'chinese': 'china', 'rockets': 'rocket', 'reusable': 'reuse',
               'flown': 'flight', 'flights': 'flight', 're-flight': 'reflight'}
    for alias, canonical in aliases.items():
        if alias in result:
            result[canonical] += result.pop(alias)
    for canonical, terms in {'china': ('中国',), 'rocket': ('火箭',),
                             'reuse': ('重复使用', '复用'),
                             'flight': ('飞行',)}.items():
        if any(term in text for term in terms):
            result[canonical] += 1
    return Counter({t: n for t, n in result.items() if t not in SEARCH_STOP and
                    not (len(t) == 1 and '\u3400' <= t <= '\u9fff' and
                         any(len(x) == 2 and t in x for x in result))})


def keyword_scores(texts, question, titles=None, *, require_subject=True):
    """Lexical relevance only: BM25, term coverage and adjacent keyword phrases."""
    query = keyword_tokens(question)
    if not query or not texts:
        return [0.0] * len(texts)
    titles = titles or [''] * len(texts)
    vectors = [keyword_tokens(text) for text in texts]
    title_vectors = [keyword_tokens(title) for title in titles]
    df = Counter(term for v, title in zip(vectors, title_vectors) for term in query if term in v or term in title)
    average = sum(sum(v.values()) for v in vectors) / len(vectors) or 1
    ordered = list(query)
    pairs = list(zip(ordered, ordered[1:]))
    quoted = re.findall(r'"([^"\n]+)"', question)
    normalize = lambda value: ' '.join(re.findall(r'[a-z0-9]+|[\u3400-\u9fff]', unicodedata.normalize('NFKC', value).lower()))
    scores = []
    for text, title, vector, tv in zip(texts, titles, vectors, title_vectors):
        from retrieval_constraints import subject_matches
        if require_subject and not subject_matches(question, title + ' ' + text):
            scores.append(0.0)
            continue
        matched = query.keys() & (vector.keys() | tv.keys())
        # One generic shared word is insufficient for a multi-keyword request.
        if not matched or (len(query) >= 3 and len(matched) < 2):
            scores.append(0.0)
            continue
        haystack = normalize(title + ' ' + text)
        if quoted and not all(normalize(phrase) in haystack for phrase in quoted):
            scores.append(0.0)
            continue
        length = sum(vector.values())
        score = 0.0
        for term in matched:
            weight = math.log(1 + (len(vectors) - df[term] + .5) / (df[term] + .5))
            tf = vector[term]
            score += weight * (tf * 2.2 / (tf + 1.2 * (.25 + .75 * length / average)) + 2 * (term in tv))
        score *= (len(matched) / len(query)) ** 2
        score *= 1 + .25 * sum(normalize(a + ' ' + b) in haystack for a, b in pairs)
        numbers = {term for term in query if term.isdigit()}
        if numbers and not numbers <= matched:
            score *= .25
        scores.append(score)
    return scores


def search(passages, question, limit=5):
    """Rank original passages without changing text, IDs or citation offsets."""
    scores = keyword_scores([p['passage'] for p in passages], question)
    ranked = [{**p, 'score': round(score, 8)} for p, score in zip(passages, scores) if score > 0]
    return sorted(ranked, key=lambda row: (-row['score'], row['passage_id']))[:limit]


def evaluate(base, passages):
    questions = read_json(base, "questions.json")
    if not isinstance(questions, list) or not questions:
        raise SafeError("Evaluation questions must be a nonempty JSON array.")
    known = {p["passage_id"] for p in passages}
    rows, hits, answerable, unanswerable, seen = [], 0, 0, 0, set()
    for item in questions:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or item["id"] in seen or not isinstance(item.get("question"), str)
                or not item["question"].strip() or type(item.get("answerable")) is not bool
                or not isinstance(item.get("expected_passage_ids"), list)
                or any(not isinstance(p, str) for p in item["expected_passage_ids"])):
            raise SafeError("Invalid evaluation question schema.")
        seen.add(item["id"])
        expected = set(item["expected_passage_ids"])
        if not expected <= known or bool(expected) != item["answerable"]:
            raise SafeError("Evaluation evidence labels do not match the corpus.")
        results = search(passages, item["question"])
        retrieved = [r["passage_id"] for r in results]
        hit = bool(expected.intersection(retrieved)) if item["answerable"] else None
        if item["answerable"]:
            answerable += 1
            hits += int(hit)
        else:
            unanswerable += 1
        rows.append({"question_id": item["id"], "expected_evidence_in_top_5": hit,
                     "retrieved_passage_ids": retrieved})
    return {"answerable_questions": answerable, "hits_at_5": hits,
            "hit_rate_at_5": hits / answerable if answerable else None,
            "manually_labeled_unanswerable_questions": unanswerable,
            "note": "Unanswerable cases are inspection-only, excluded from hit rate. Search scores do not establish answerability.",
            "questions": rows}


def private_output(base, result):
    external_directory(base)
    # Exclusive creation directly under the validated root avoids following an
    # existing output path into another directory. No logs or indexes are persisted.
    path = base / ("result-" + uuid.uuid4().hex + ".json")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SafeError("Invalid command arguments. Use --help for syntax.")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--mode", required=True, choices=("demo", "private"))
        parser.add_argument("command", choices=("search", "evaluate"))
        parser.add_argument("--question", help="Search question; private queries also remain in shell history.")
        parser.add_argument("--question-file", help="UTF-8 question file relative to the selected data directory.")
        args = parser.parse_args(argv)
        base = demo_directory() if args.mode == "demo" else private_directory()
        if args.question and args.question_file:
            raise SafeError("Choose either --question or --question-file.")
        question = args.question
        if args.question_file:
            question = safe_file(base, args.question_file).read_text(encoding="utf-8")
        if args.command == "search" and not (question and question.strip()):
            raise SafeError("Search requires a nonempty --question.")
        passages = load_passages(base)
        if args.command == "evaluate":
            result = evaluate(base, passages)
        else:
            result = {"results": search(passages, question),
                      "note": "Lexical matches only; scores do not prove answerability or factual support."}
        if args.mode == "private":
            private_output(base, result)
            print("Private result saved in the configured data directory as result-*.json. No passages printed.")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SafeError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        # Never print exception values, paths, JSON fragments, or tracebacks.
        print("Processing failed. Check UTF-8 input, JSON schemas, dates, and filesystem permissions locally.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
