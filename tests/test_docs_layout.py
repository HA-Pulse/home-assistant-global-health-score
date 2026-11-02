"""README budget and the docs/ layout: short README sections link to their full page, nothing under docs/ is orphaned.

The rule is in CONTRIBUTING.md (Documentation). Links are checked offline: a repository URL must name a file of this
checkout (and an anchor a heading of it), so the test passes on dev before the pages reach main.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
REPO = "HA-Pulse/home-assistant-global-health-score"
BLOB = f"https://github.com/{REPO}/blob/main/"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"
BUDGET = 400
NOTICE = "> **Short version.** "
BACK_MD = f"[← Back to the README]({BLOB}README.md)"
BACK_YAML = f"# Back to the README: {BLOB}README.md"
DETAILED = "**Detailed documentation**"
LINK = re.compile(r"\]\(([^)\s]+)\)|src=\"([^\"]+)\"")
URL = re.compile(r"https?://[^\s)\"'>]+")
REGISTRY = json.loads(
    (ROOT / "tests" / "data" / "readme_sections.json").read_text(encoding="utf-8")
)["sections"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lower case, punctuation removed, spaces to hyphens."""
    text = re.sub(r"[*`]|\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    kept = "".join(c for c in text if c in "-_ " or unicodedata.category(c)[0] in "LN")
    return kept.replace(" ", "-")


def _anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors = set()
    fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        match = None if fence else re.match(r"#{1,6} (.+)", line)
        if match:
            slug = _slug(match.group(1))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """README '## ' sections; a section ends at the next '## ' heading or at its closing '---' line."""
    found: list[tuple[str, list[str]]] = []
    closed = True
    for line in text.splitlines():
        if line.startswith("## "):
            found.append((line[3:], []))
            closed = False
        elif line.strip() == "---":
            closed = True
        elif not closed:
            found[-1][1].append(line)
    return found


def _docs_files() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*") if p.is_file())


def _pages() -> list[Path]:
    return [p for p in _docs_files() if p.suffix in (".md", ".yaml")]


def _links(path: Path) -> list[str]:
    text = _read(path)
    if path.suffix == ".yaml":
        return [u for line in text.splitlines() if line.startswith("# ") for u in URL.findall(line)]
    return [a or b for a, b in LINK.findall(text)]


def _target(link: str, source: Path) -> tuple[Path | None, str]:
    """The checkout file and anchor a link names; None for external links."""
    url, _, anchor = link.partition("#")
    if link.startswith("#"):
        return source, anchor
    for prefix in (BLOB, RAW):
        if url.startswith(prefix):
            return ROOT / url[len(prefix) :], anchor
    return None, anchor


def test_readme_stays_within_the_line_budget() -> None:
    lines = len(_read(README).splitlines())
    assert lines <= BUDGET, (
        f"README has {lines} lines, budget {BUDGET}: move details to docs/ (CONTRIBUTING.md)"
    )


def test_readme_sections_match_the_registry() -> None:
    assert [h for h, _ in _sections(_read(README))] == [s["heading"] for s in REGISTRY]


def _notice_problems(readme: str) -> list[str]:
    """Short sections without the notice under the heading or the link at the end; notices on full sections."""
    sections = dict(_sections(readme))
    problems = []
    for entry in REGISTRY:
        content = [x for x in sections.get(entry["heading"], []) if x.strip()]
        if "full" not in entry:
            if any(x.startswith(NOTICE) for x in content):
                problems.append(f"{entry['heading']}: notice on a section that is not shortened")
            continue
        url = BLOB + entry["full"]
        if not (content and content[0].startswith(NOTICE) and f"]({url})" in content[0]):
            problems.append(
                f"{entry['heading']}: no '{NOTICE.strip()}' notice linking {url} under the heading"
            )
        if not (content and re.fullmatch(rf"\[[^\]]+ →\]\({re.escape(url)}\)", content[-1])):
            problems.append(f"{entry['heading']}: last line is not the link '[All … →]({url})'")
    return problems


def test_short_sections_link_their_full_page_at_top_and_bottom() -> None:
    assert _notice_problems(_read(README)) == []


def test_a_short_section_without_its_links_fails() -> None:
    readme = _read(README)
    url = BLOB + "docs/attributes.md"
    cut = readme.replace(f"[All attributes →]({url})\n", "").replace(
        f"> **Short version.** The full list of all attributes with types and meaning is in [docs/attributes.md]({url}).\n",
        "",
    )
    assert cut != readme
    assert _notice_problems(cut) == [
        f"Sensor Attributes: no '{NOTICE.strip()}' notice linking {url} under the heading",
        f"Sensor Attributes: last line is not the link '[All … →]({url})'",
    ]


def test_every_docs_file_is_linked_from_the_readme() -> None:
    readme = _read(README)
    linked = {_target(link, README)[0] for link in _links(README)}
    assert [p for p in _docs_files() if p not in linked] == []
    block = readme.split(DETAILED, 1)[1].split("\n\n", 1)[0]
    in_block = {_target(a or b, README)[0] for a, b in LINK.findall(block)}
    assert [p for p in _pages() if p not in in_block] == []


def test_every_docs_page_is_the_full_page_of_a_readme_section() -> None:
    full = {ROOT / s["full"].partition("#")[0] for s in REGISTRY if "full" in s}
    assert [p for p in _pages() if p.suffix == ".md" and p not in full] == []


@pytest.mark.parametrize("page", _pages(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_docs_page_starts_with_a_link_back_to_the_readme(page: Path) -> None:
    lines = _read(page).splitlines()
    if page.suffix == ".md":
        assert lines[0] == BACK_MD
    else:
        assert lines[1] == BACK_YAML


@pytest.mark.parametrize("source", [README, *_pages()], ids=lambda p: str(p.relative_to(ROOT)))
def test_every_repository_link_resolves(source: Path) -> None:
    broken = []
    for link in _links(source):
        if source == README and not link.startswith(("http://", "https://", "#", "mailto:")):
            broken.append(f"{link}: relative link (HACS shows the README outside GitHub)")
            continue
        path, anchor = _target(link, source)
        if path is None:
            continue
        if not path.is_file():
            broken.append(f"{link}: no such file")
        elif anchor and path.suffix == ".md" and anchor not in _anchors(_read(path)):
            broken.append(f"{link}: no such heading")
    assert broken == []


def test_readme_attribute_rows_are_rows_of_the_full_table() -> None:
    rows = [x for x in dict(_sections(_read(README)))["Sensor Attributes"] if x.startswith("| `")]
    full = set(_read(DOCS / "attributes.md").splitlines())
    assert rows
    assert [r for r in rows if r not in full] == []


def test_card_yaml_files_carry_their_version_line() -> None:
    first = {p.name: _read(p).splitlines()[0] for p in sorted((DOCS / "cards").glob("*.yaml"))}
    assert first == {
        "lite.yaml": "# HAGHS Lite v1.4 (Quick Check)",
        "pro.yaml": "# HAGHS Pro v1.4 (Command Center)",
    }
