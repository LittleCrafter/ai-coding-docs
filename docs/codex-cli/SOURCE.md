# Source: Codex CLI

- **Owner:** OpenAI
- **Canonical sources:**
  - https://learn.chatgpt.com/docs/ — the documentation catalogue listed in
    `https://developers.openai.com/codex/llms.txt` (most of this folder).
  - https://github.com/openai/codex (`docs/` directory) — the versioned
    Markdown files shipped with the repository (the Contributor License
    Agreement, the license page, the contributing guide, and the Open Source
    Fund pages).
- **License:** Apache License 2.0 — see [`./LICENSE`](./LICENSE) and
  [`./NOTICE`](./NOTICE), the upstream repository's license and notice files,
  included here verbatim and byte-identical to upstream. They are the only
  files in this folder reproduced that way: the mirrored pages carry the
  changes listed under **How mirrored** below. They cover the files mirrored
  from the repository (the Git-tree origin above); the pages mirrored from the
  documentation catalogue are reproduced from their published form. Pages
  assembled from both origins (such as [`./config.md`](./config.md), which
  starts from the repository's configuration reference and embeds catalogue
  content) carry repository text under the license above and embedded
  catalogue text from the documentation portal.
- **How mirrored:** scraping. The Git tree of `openai/codex` is listed through
  the GitHub API and direct Markdown children of `docs/` are downloaded from
  `raw.githubusercontent.com`; the documentation catalogue is read from the
  `codex/llms.txt` index and each page is downloaded as its published Markdown.
  Files are then modified for plain-Markdown reading: Astro/MDX components are
  converted to standard Markdown (headings, lists, tables, code blocks,
  collapsible sections), a leading frontmatter block is dropped with its title
  kept as a heading, site-absolute and cross-documentation links are rewritten
  to local relative paths when the target is mirrored here, and reference stubs
  whose full guide is published separately are not mirrored so that each
  document appears once.

Content © OpenAI. Licensed under the Apache License, Version 2.0; you may
not use the repository files except in compliance with the License. The files
mirrored from the repository are **modified** where any of the conversions
below applied to them: the Astro/MDX component conversion (components rendered
as headings, lists, tables, code blocks, and blockquotes), the link rewriting
to local relative paths, the de-duplication of reference stubs whose guide is
published separately, and the replacement of a leading frontmatter block by
its title as a heading. A file that needed none of these (the Contributor
License Agreement, for example) is reproduced as published. This statement of
what was changed is made here as Apache 2.0 §4(b) requires, and the license
text and upstream NOTICE are included in this folder as §4 requires.
