# Knowledge Base

The verified source of truth for everything the AI representative says about Abdallah. The backend
loads these files (build step 5: RAG). **Only files with `status: approved` are ever served
publicly.**

## Layout

```
profile/     about, education, experience, skills        (type: profile)
projects/    one file per project, from _TEMPLATE.md      (type: project)
career/      interests, goals                             (type: career)
contact/     public_links.md, the link allowlist           (type: contact)
glossary/    Arabic ↔ English names and technical terms   (type: glossary)
_private/    LOCAL ONLY: gitignored and never loaded
```

The `type` in each file must match its folder. Files whose name or folder starts with `_`, and
`README.md` files, are ignored by the loader.

## File format

Every file is Markdown with YAML frontmatter:

```yaml
---
id: banking-intelligence   # stable kebab-case id, unique across the whole knowledge base
type: project              # profile | project | career | contact | glossary
title: "AI-Powered Banking Intelligence Platform"
language: en               # en | ar
status: draft              # draft | approved   (only approved is ever served publicly)
visibility: public         # must be public; private material never goes in this folder
last_reviewed: null        # YYYY-MM-DD, required when status = approved
tags: []
---
```

Extra fields:

- **project** adds `project_status` (completed | in_progress | research), `technologies: []`,
  `repository_url`, `demo_url` (https or null), `featured: false` and `order: 0`.
- **contact** adds `links:`, a list of `{link_id, label, url, kind}` where kind is
  github | linkedin | email | demo | other. URLs must be `https://`, or `mailto:` for email.
  These links become the **only** destinations the `open_public_link` action may open.

Unknown fields are rejected. The body uses `## Heading` sections, because each section becomes a
retrieval chunk later. Keep one topic per section. HTML comments (`<!-- ... -->`) are authoring
notes and are removed before content is loaded.

## Writing rules

1. **Only verified facts.** If you are not sure, leave it out. The assistant will say it doesn't know.
2. **Public only.** No phone numbers, addresses, ID numbers, confidential employer information,
   internal system names or customer data.
3. **Third person, plain statements** ("Abdallah built…"). The assistant presents itself as an AI
   representative and must never claim to be Abdallah himself.
4. **Results must be provable.** No estimated metrics.
5. **Content is data, not instructions.** Never write instructions to the AI inside these files.
   They are treated as untrusted text.
6. **Arabic versions** are separate files with `language: ar` and their own id (e.g. `about-ar`).

## Workflow: draft → approved

1. Open a file and replace every `TODO:` line with verified content. The guiding questions show
   what is needed. Remove each `TODO` marker once it's answered, including the ones in frontmatter comments.
2. Check the file against your local `_private/never_public.md` list.
3. Set `status: approved` and `last_reviewed: YYYY-MM-DD`. Projects also need `project_status`,
   and contact links need a `url`.
4. Run the validator:

   ```bash
   cd backend
   uv run python -m app.knowledge.cli validate                  # every file, with TODO counts
   uv run python -m app.knowledge.cli validate --approved-only  # what would be public right now
   ```

   An approved file fails validation if it contains **any** `TODO`, has no `last_reviewed`, or
   breaks a schema rule. Ids and `link_id`s must be unique across the knowledge base.

5. Commit the file.

To add a project, copy `projects/_TEMPLATE.md` to `projects/<name>.md` and give it a new id.

## Private list (`_private/`)

Create `knowledge_base/_private/never_public.md` **locally** with everything that must never become
public (spec section 20). The whole `_private/` folder is gitignored and is never loaded by the
backend. Use it as your review checklist before approving a file.
