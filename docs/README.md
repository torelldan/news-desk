# News Desk documentation

Documentation for the News Desk, a prepared-citizen situation desk for Thompson's Station, TN 37179 (live at https://torelldan.github.io/news-desk/).

| Document | For | What's in it |
|---|---|---|
| [ONE-PAGER.md](ONE-PAGER.md) | Anyone; start here | What the desk is for and how it works, in one page |
| [KDD.md](KDD.md): Knowledge Design Document | Maintainers | Purpose, sections, severity scale, every source and its fallback, the rules (dedupe, clustering, What changed, Storm watch, static cards), design decisions, limitations, glossary |
| [PFL.md](PFL.md): Process Flow Layout | Maintainers and Daniel | Architecture diagram, daily refresh flow, single-item classification flow, step tables with failure behaviour, and a plain-language operations guide (manual refresh, approving a change) |

Diagrams are written in Mermaid and render directly on GitHub.

These documents describe `main` as of commit `c175c1d` (PR #17, Nov 11, 2026). When the code changes, update the matching section. Severity rules live in `scripts/boards.py` and `scripts/citizen.py`; story matching is duplicated in `template.html`.
