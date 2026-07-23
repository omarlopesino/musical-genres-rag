#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Generates the dataset from a MusicBrainz TSV dump.

Run it through the following command:
    uv run scripts/generate-dataset.py <path-to-mbdump>

<path-to-mbdump> must be replaced by the existing path of the musicbrainz postgres database dump.
It is a folder containing, for each table, TSV files.

If you want to override the genres used, use --genres parameter. Example:
    uv run scripts/generate-dataset.py ../mbdump/mbdump --genres "rap,jazz,bebop"

The genre descriptions are gathered from Wikidata.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

DEFAULT_GENRES = [
    "pop",
    "jazz",
    "rock",
    "hip hop",
    "acid jazz",
    "dixieland",
    "jazz fusion",
    "pop rock",
    "rap rock",
    "synth-pop",
]

REQUIRED_FILES = [
    "genre",
    "genre_alias",
    "instrument",
    "l_genre_genre",
    "l_genre_instrument",
    "l_genre_url",
    "l_instrument_url",
    "link",
    "link_type",
    "url",
]

# Link types are identified by name rather than by id: the numeric ids are
# specific to one dump, and a stale constant fails silently as an empty result.
SUBGENRE = ("genre", "genre", "subgenre")
FUSION = ("genre", "genre", "fusion of")
GENRE_INSTRUMENT = ("genre", "instrument", "associated instrument")
GENRE_WIKIDATA = ("genre", "url", "wikidata")
INSTRUMENT_WIKIDATA = ("instrument", "url", "wikidata")

USER_AGENT = "musical-genres-rag/1.0 (https://github.com/; seed data extraction)"


# --------------------------------------------------------------------------- #
# dump reading
# --------------------------------------------------------------------------- #

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def unescape(value):
    """Decode one MusicBrainz TSV field. ``\\N`` is NULL."""
    if value == r"\N":
        return None
    if "\\" not in value:
        return value
    out = []
    i = 0
    while i < len(value):
        char = value[i]
        if char == "\\" and i + 1 < len(value):
            out.append(_ESCAPES.get(value[i + 1], value[i + 1]))
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def read_tsv(mbdump, name):
    """Stream one dump file a row at a time. ``url`` is 2.5 GB -- never slurp."""
    with open(mbdump / name, encoding="utf-8", newline="") as handle:
        for line in handle:
            yield [unescape(v) for v in line.rstrip("\n").split("\t")]


def resolve_link_ids(mbdump, wanted):
    """Map each (entity0, entity1, name) link type to the set of its link ids."""
    type_ids = {}
    for row in read_tsv(mbdump, "link_type"):
        key = (row[4], row[5], row[6])
        if key in wanted:
            type_ids[row[0]] = key

    missing = wanted - set(type_ids.values())
    if missing:
        die("link types not found in the dump: " + ", ".join(map(str, sorted(missing))))

    links = defaultdict(set)
    for row in read_tsv(mbdump, "link"):
        key = type_ids.get(row[1])
        if key is not None:
            links[key].add(row[0])
    return links


def resolve_urls(mbdump, url_ids):
    """Stream the 2.5 GB url table, keeping only the handful of ids we need."""
    found = {}
    if not url_ids:
        return found
    for row in read_tsv(mbdump, "url"):
        if row[0] in url_ids:
            found[row[0]] = row[2]
            if len(found) == len(url_ids):
                break
    return found


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #


def select_genres(mbdump, requested):
    """Resolve the requested names to MusicBrainz genre ids, in the given order."""
    names = {}
    by_name = {}
    for row in read_tsv(mbdump, "genre"):
        names[row[0]] = row[2]
        by_name[row[2].casefold()] = row[0]

    by_alias = {}
    for row in read_tsv(mbdump, "genre_alias"):
        key = row[2].casefold()
        if key not in by_name:
            by_alias.setdefault(key, row[1])

    selected, unknown = [], []
    for requested_name in requested:
        key = requested_name.casefold()
        genre_id = by_name.get(key) or by_alias.get(key)
        if genre_id is None:
            unknown.append(requested_name)
            continue
        if names[genre_id] .casefold() != key:
            log(f"  {requested_name!r} is an alias of {names[genre_id]!r}")
        if genre_id not in selected:
            selected.append(genre_id)

    if unknown:
        die("no MusicBrainz genre or alias matches: " + ", ".join(repr(u) for u in unknown))
    return selected, names


def build_hierarchy(mbdump, links, selected):
    """(child, parent) pairs from subgenre and 'fusion of', restricted to the selection."""
    subgenre, fusion = links[SUBGENRE], links[FUSION]
    chosen = set(selected)
    parents = defaultdict(set)
    for row in read_tsv(mbdump, "l_genre_genre"):
        if row[1] in subgenre:
            parent, child = row[2], row[3]
        elif row[1] in fusion:
            child, parent = row[2], row[3]
        else:
            continue
        if parent in chosen and child in chosen and parent != child:
            parents[child].add(parent)
    return parents


def direct_instruments(mbdump, links, selected):
    associated = links[GENRE_INSTRUMENT]
    chosen = set(selected)
    direct = defaultdict(set)
    for row in read_tsv(mbdump, "l_genre_instrument"):
        if row[1] in associated and row[2] in chosen:
            direct[row[2]].add(row[3])
    return direct


def propagate(selected, parents, direct):
    """Roll instruments up the hierarchy, then push the result back down.

    A genre encompasses the instruments of its subgenres (phase 1), and a
    subgenre inherits the instruments of its parents (phase 2). Both phases are
    monotone fixpoints, so a cycle in the dump cannot cause infinite recursion.
    Running the two phases once each -- rather than iterating them together --
    is deliberate: the selected graph is usually connected, and alternating
    up/down passes to a joint fixpoint would flood every instrument into every
    genre.
    """
    children = defaultdict(set)
    for child, child_parents in parents.items():
        for parent in child_parents:
            children[parent].add(child)

    up = {g: set(direct.get(g, ())) for g in selected}
    changed = True
    while changed:
        changed = False
        for genre in selected:
            for child in children.get(genre, ()):
                if not up[child] <= up[genre]:
                    up[genre] |= up[child]
                    changed = True

    effective = {g: set(up[g]) for g in selected}
    changed = True
    while changed:
        changed = False
        for genre in selected:
            for parent in parents.get(genre, ()):
                if not effective[parent] <= effective[genre]:
                    effective[genre] |= effective[parent]
                    changed = True
    return effective


def load_instruments(mbdump, instrument_ids):
    """name and dump description for each instrument, keyed by MusicBrainz id."""
    found = {}
    for row in read_tsv(mbdump, "instrument"):
        if row[0] in instrument_ids:
            found[row[0]] = (row[2], (row[7] or "").strip())
    missing = instrument_ids - set(found)
    if missing:
        die("instruments referenced but absent from the dump: " + ", ".join(sorted(missing)))
    return found


def wikidata_ids(mbdump, links, table, entity_ids, link_key):
    """MusicBrainz entity id -> Wikidata Q-id, via the dump's own wikidata links."""
    wikidata = links[link_key]
    url_of = {}
    for row in read_tsv(mbdump, table):
        if row[1] in wikidata and row[2] in entity_ids:
            url_of[row[2]] = row[3]

    resolved = resolve_urls(mbdump, set(url_of.values()))
    out = {}
    for entity_id, url_id in url_of.items():
        url = resolved.get(url_id)
        if url:
            out[entity_id] = url.rstrip("/").rsplit("/", 1)[-1]
    return out


# --------------------------------------------------------------------------- #
# descriptions
# --------------------------------------------------------------------------- #


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_description(qid):
    """Prose summary for a Wikidata entity, preferring its English Wikipedia article."""
    entity = fetch_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    claims = entity["entities"][qid]
    title = claims.get("sitelinks", {}).get("enwiki", {}).get("title")
    if title:
        quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
        summary = fetch_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quoted}")
        text = summary.get("extract", "")
        if text.strip():
            return normalise(text), summary.get("content_urls", {}).get("desktop", {}).get("page", "")
    fallback = claims.get("descriptions", {}).get("en", {}).get("value", "")
    return normalise(fallback), f"https://www.wikidata.org/wiki/{qid}"


def normalise(text):
    """Collapse to a single line so every CSV record is one physical line."""
    return " ".join(text.split())


class Descriptions:
    def __init__(self, path, refresh):
        self.path = path
        self.refresh = refresh
        self.cache = {}
        if path.exists() and not refresh:
            self.cache = json.loads(path.read_text(encoding="utf-8"))
        self.fetched = 0

    def get(self, qid):
        if qid not in self.cache:
            log(f"  fetching {qid}")
            text, source = fetch_description(qid)
            self.cache[qid] = {"text": text, "source": source}
            self.fetched += 1
            time.sleep(0.2)
        return self.cache[qid]["text"]

    def save(self):
        ordered = {k: self.cache[k] for k in sorted(self.cache)}
        self.path.write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #


def check_copyable(rows, path):
    """Guard the assumptions data/load.sql's COPY statements rely on."""
    for row in rows:
        for cell in row:
            cell = str(cell)
            if not cell.strip():
                die(f"{path}: empty field would be read as NULL by COPY: {row!r}")
            if "\n" in cell or "\r" in cell:
                die(f"{path}: embedded newline in {row!r}")
            if r"\N" in cell:
                die(f"{path}: literal \\N would be ambiguous in {row!r}")


def write_csv(path, header, rows):
    check_copyable(rows, path)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    log(f"  {path} ({len(rows)} rows)")


def log(message):
    print(message, file=sys.stderr)


def die(message):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------- #


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("mbdump", type=Path, help="directory holding the MusicBrainz TSV files")
    parser.add_argument(
        "--genres",
        default=",".join(DEFAULT_GENRES),
        help="comma-separated genre names or aliases (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
        help="output directory (default: ./data)",
    )
    parser.add_argument("--refresh", action="store_true", help="re-fetch descriptions")
    args = parser.parse_args()

    mbdump = args.mbdump
    if not mbdump.is_dir():
        die(f"{mbdump} is not a directory")
    absent = [name for name in REQUIRED_FILES if not (mbdump / name).is_file()]
    if absent:
        die(f"{mbdump} is missing dump files: {', '.join(absent)}")

    requested = [name.strip() for name in args.genres.split(",") if name.strip()]
    if not requested:
        die("--genres is empty")

    args.out.mkdir(parents=True, exist_ok=True)

    log("resolving genres")
    selected, genre_names = select_genres(mbdump, requested)
    log(f"  {len(selected)} genres: {', '.join(genre_names[g] for g in selected)}")

    links = resolve_link_ids(
        mbdump, {SUBGENRE, FUSION, GENRE_INSTRUMENT, GENRE_WIKIDATA, INSTRUMENT_WIKIDATA}
    )

    parents = build_hierarchy(mbdump, links, selected)
    hierarchy_rows = sum(len(p) for p in parents.values())
    log(f"building hierarchy\n  {hierarchy_rows} parent links")

    direct = direct_instruments(mbdump, links, selected)
    log("collecting instruments")
    for genre in selected:
        if direct.get(genre):
            log(f"  {genre_names[genre]}: {len(direct[genre])} direct")

    effective = propagate(selected, parents, direct)
    instrument_ids = set().union(*effective.values()) if effective else set()
    instruments = load_instruments(mbdump, instrument_ids)
    log(f"  {len(instrument_ids)} instruments after propagation")

    log("resolving wikidata links")
    genre_qids = wikidata_ids(mbdump, links, "l_genre_url", set(selected), GENRE_WIKIDATA)
    needs_wikidata = {i for i, (_, desc) in instruments.items() if not desc}
    instrument_qids = wikidata_ids(
        mbdump, links, "l_instrument_url", needs_wikidata, INSTRUMENT_WIKIDATA
    )

    descriptions = Descriptions(args.out / "descriptions.json", args.refresh)
    log("descriptions")
    genre_text = {}
    for genre in selected:
        qid = genre_qids.get(genre)
        if qid is None:
            die(f"{genre_names[genre]!r} has no wikidata link and no description available")
        genre_text[genre] = descriptions.get(qid)

    instrument_text = {}
    for instrument_id, (name, dump_desc) in instruments.items():
        if dump_desc:
            instrument_text[instrument_id] = normalise(dump_desc)
            continue
        qid = instrument_qids.get(instrument_id)
        if qid is None:
            die(f"{name!r} has neither a dump description nor a wikidata link")
        instrument_text[instrument_id] = descriptions.get(qid)
    descriptions.save()
    if descriptions.fetched:
        log(f"  fetched {descriptions.fetched}, cached in {descriptions.path}")

    # Surrogate ids: genres in the order requested, instruments alphabetically.
    genre_id = {mb: n for n, mb in enumerate(selected, start=1)}
    ordered_instruments = sorted(instrument_ids, key=lambda i: instruments[i][0])
    instrument_id = {mb: n for n, mb in enumerate(ordered_instruments, start=1)}

    log("writing")
    write_csv(
        args.out / "genre.csv",
        ["id", "name", "description"],
        [[genre_id[g], genre_names[g], genre_text[g]] for g in selected],
    )
    write_csv(
        args.out / "genre_hierarchy.csv",
        ["genre", "parent"],
        sorted(
            (genre_id[child], genre_id[parent])
            for child, child_parents in parents.items()
            for parent in child_parents
        ),
    )
    write_csv(
        args.out / "instrument.csv",
        ["id", "name", "description"],
        [
            [instrument_id[i], instruments[i][0], instrument_text[i]]
            for i in ordered_instruments
        ],
    )
    write_csv(
        args.out / "instrument_genres.csv",
        ["instrument", "genre"],
        sorted(
            (instrument_id[i], genre_id[g])
            for g in selected
            for i in effective[g]
        ),
    )


if __name__ == "__main__":
    main()
