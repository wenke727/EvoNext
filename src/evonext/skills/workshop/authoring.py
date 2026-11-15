"""Shared authoring checks. Mechanical validity is not semantic approval."""
import posixpath
import re
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from evonext.contracts.skills import SkillAsset, skill_content_hash
from evonext.contracts.trajectory import ContractError
from evonext.skills.workshop.library import validate_document


def markdown(text):
    parser = MarkdownIt("commonmark", {"html": False})
    # Parse every link for validation below. No HTML is rendered or executed here.
    parser.validateLink = lambda _: True
    return parser.parse(text)


def validate_files(skill_id, files):
    if "SKILL.md" not in files:
        raise ContractError("Draft requires complete SKILL.md")
    validate_document(skill_id, files["SKILL.md"])
    try:
        assets = tuple(SkillAsset(path=p, content=c) for p, c in files.items() if p != "SKILL.md")
    except ValueError as exc:
        raise ContractError("Invalid Skill attachment path or content") from exc
    skill_content_hash(files["SKILL.md"], assets, "v2")
    # Local Markdown links must resolve inside this frozen bundle.
    edges = {}
    for path, text in files.items():
        if not path.endswith(".md"):
            continue
        tokens = markdown(text)
        edges[path] = set()
        pending = list(tokens)
        links = []
        while pending:
            token = pending.pop()
            pending.extend(token.children or ())
            if token.type in {"link_open", "image"}:
                links.append(token.attrGet("href" if token.type == "link_open" else "src"))
        for target in links:
            url = urlsplit(target.strip("<>"))
            if url.scheme in {"https", "http"}:
                continue
            if url.scheme or url.netloc or "\\" in target:
                raise ContractError("Unsupported Skill link")
            destination = posixpath.normpath(posixpath.join(posixpath.dirname(path),
                                                           unquote(url.path))) if url.path else path
            if destination not in files:
                raise ContractError(f"Missing local reference: {destination}")
            edges[path].add(destination)
            if url.fragment:
                destination_tokens = markdown(files[destination])
                headings = [destination_tokens[i + 1].content for i, t in enumerate(destination_tokens)
                            if t.type == "heading_open"]
                anchors, counts = set(), {}
                for heading in headings:
                    anchor = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                    count = counts.get(anchor, 0)
                    counts[anchor] = count + 1
                    anchors.add(f"{anchor}-{count}" if count else anchor)
                if unquote(url.fragment) not in anchors:
                    raise ContractError(f"Missing reference anchor: {target}")
    reachable, pending = set(), ["SKILL.md"]
    while pending:
        path = pending.pop()
        if path not in reachable:
            reachable.add(path)
            pending.extend(edges.get(path, ()))
    if any(p.startswith("references/") and p.endswith(".md") and p not in reachable for p in files):
        raise ContractError("Reference documents must be reachable from SKILL.md")
    return files


def lint(files):
    text = files["SKILL.md"]
    warnings = []
    if len(text.encode()) > 12 * 1024 or len(text.splitlines()) > 250:
        warnings.append("Long main document: consider an explicit diet review.")
    if re.search(r"(?m)^#{1,6}\s+.*20\d\d[-/]\d", text):
        warnings.append("Dated narrative: prefer a reusable condition and action.")
    if len(text.split("---", 2)[1]) > 1500:
        warnings.append("Long metadata: keep discovery focused on stable triggers.")
    return warnings[:3]


def diet(files, headings):
    """Move complete level-two sections verbatim; no model-authored rule rewriting."""
    document = files["SKILL.md"]
    if not headings or len(set(headings)) != len(headings):
        raise ContractError("Diet needs distinct section headings")
    destination = "references/diet.md"
    if destination in files:
        raise ContractError("Diet reference already exists; review manually before another diet")
    # Reference-style links and nested local links need a richer Markdown parser.
    # Stop explicitly instead of silently breaking their meaning during relocation.
    if re.search(r"(?m)^\s*\[[^\]]+\]:", document):
        raise ContractError("Reference-style links require manual diet")
    heading_lines = {t.map[0] for t in markdown(document)
                     if t.type == "heading_open" and t.tag == "h2" and t.level == 0 and t.map}
    matches = [m for m in re.finditer(r"(?m)^## (.+)\r?$", document)
               if document[:m.start()].count("\n") in heading_lines]
    available = [m.group(1).strip() for m in matches]
    if any(available.count(h) != 1 for h in headings):
        raise ContractError("Diet heading is absent or ambiguous")
    chunks, moved, cursor = [], [], 0
    for i, match in enumerate(matches):
        if match.group(1).strip() not in headings:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(document)
        section = document[match.start():end]
        if re.search(r"!?\[[^\]]*\]\(", section) or "```" in section or "~~~" in section:
            raise ContractError("Linked or fenced sections require manual diet")
        chunks.extend([document[cursor:match.start()],
                       f"{match.group(0)}\nRead [the full procedure](references/diet.md) "
                       "before applying this section.\n\n"])
        moved.append(section)
        cursor = end
    chunks.append(document[cursor:])
    proposed = {**files, "SKILL.md": "".join(chunks), destination: "\n".join(moved)}
    if len(proposed["SKILL.md"].encode()) > len(document.encode()) * .8:
        raise ContractError("Diet must reduce the main document by at least 20 percent")
    return proposed
