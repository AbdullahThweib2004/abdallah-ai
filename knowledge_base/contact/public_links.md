---
id: public-links
type: contact
title: "Public Contact Links"
language: en
status: draft                 # draft | approved (only approved is ever served publicly)
visibility: public
last_reviewed: null           # YYYY-MM-DD, required when status = approved
tags: []
# These links become the allowlist for the `open_public_link` UI action (build step 6).
# url: https:// only, except kind=email which must be mailto:. Leave url null until verified.
links:
  - link_id: github
    label: "GitHub"
    url: null                 # TODO: https://github.com/<username>
    kind: github
  - link_id: linkedin
    label: "LinkedIn"
    url: null                 # TODO: https://www.linkedin.com/in/<handle>
    kind: linkedin
  - link_id: email
    label: "Email"
    url: null                 # TODO: mailto:<address> (only an address you want to be public)
    kind: email
---

# Public Contact Links

## Preferred contact method

TODO: How should visitors contact you first (email, LinkedIn, other)?

## Response expectations

TODO: Optional: how quickly do you usually reply? If you prefer not to say, write "Not shared."

## Other public links

TODO: Are there other public links (portfolio demos, blog, Hugging Face, Kaggle)? Add each to the `links` list in the frontmatter with kind `demo` or `other`.
