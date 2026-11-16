---
id: ai-developer-assistant
type: project
title: "AI Developer Assistant (RAG + MCP)"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [rag, mcp, llm, developer-tools, security]
project_status: completed
technologies: [Python, FastAPI, Chroma, sentence-transformers, MCP Python SDK, Anthropic API, OpenAI-compatible APIs, React, TypeScript, Vite, Tailwind CSS, pytest, uv]
repository_url: https://github.com/AbdullahThweib2004/ai-developer-assistant
demo_url: null
featured: true
order: 1
---
# Project: AI Developer Assistant

## Project ID
See frontmatter.

## Status
See frontmatter. All eight planned phases are done.

## One-line summary
An AI assistant that combines retrieval-augmented generation (RAG) with the Model Context Protocol (MCP) to help engineers understand codebases, investigate errors and work with GitHub issues, where any write action needs explicit human approval.

## Problem
Understanding an unfamiliar codebase or chasing a bug means jumping between source files, documentation and GitHub issues. Generic chatbots are not grounded in the actual code, and an AI tool with write access to GitHub is risky if it can be manipulated.

## Target users
Software engineers who need to understand a repository or investigate a bug.

## Abdullah's contribution
<!-- TODO: Solo project? If yes, write "Designed and built the whole project." Anything you want to highlight as the part you are proudest of? -->

## Architecture
A repository goes through an ingestion pipeline that only reads safe files, then is split into chunks, embedded with a local embedding model and stored in Chroma. At question time a retriever finds the most relevant chunks and the LLM answers only from that context, with citations to files and line ranges.

The same retrieval and file-access code is exposed to external MCP clients through a read-only MCP server. A GET-only GitHub client reads issues and pull requests from an allowlist of repositories. On top, an orchestrator runs a bounded tool-use loop through a real MCP client session, injects the session's project and repository itself, validates citations, and records a trace. Issue creation goes through a separate approval service. The assistant is available as a web app, a CLI and an MCP server.

## Technologies
See frontmatter.

## Data sources
The repository the user chooses to index (code, Markdown, text, config files and PDFs), and GitHub issues and pull requests from allowlisted repositories.

## Key implementation details
- Answers are grounded in retrieved code and cite files and line ranges.
- Error investigation: the user describes a bug or pastes a stack trace and gets the relevant code paths and ranked likely causes, with GitHub issues treated as leads, not proof.
- Everything the assistant reads (code, docs, GitHub text) is treated as untrusted data. The model only gets read-only tools and cannot choose the project or repository.
- Secret files such as .env and keys are never read or indexed.
- Issue creation is off by default. It needs a separate token, a write allowlist, and a human who types the repository name to approve. Approvals are single-use, bound to the exact draft, and written to an audit log.
- The web API binds to localhost and requires a per-launch token.
- Works with Anthropic, OpenAI-compatible providers (OpenRouter, Groq) and local models through Ollama.
- A demo mode runs with no API keys and no network, using fake embeddings, a scripted LLM and mocked GitHub.

## Challenges and trade-offs
- Prompt injection: code, documentation and GitHub issues can contain instructions aimed at the model, so all of it is handled as data and write actions are kept out of the model's control.
- Balancing usefulness with safety for GitHub write access, solved with a draft-then-human-approval flow instead of letting the model post directly.
<!-- TODO: What was the hardest problem you hit while building it, and how did you solve it? -->

## Results (only verified results)
From the project's own evaluation:
- Prompt-injection cases (6, live): 0 forbidden tool calls, 0 leaks, 0 unrequested issue drafts.
- Orchestration (12 cases, live): tool selection 0.917, citation validity 1.0, expected evidence 1.0.
- Retrieval on the sample project (12 queries): Recall@5 1.000, MRR 0.958.
- Retrieval on the assistant's own repository (15 queries): Recall@5 0.867, MRR 0.549.

## Limitations
- Retrieval ranking is weaker on a larger real repository (MRR 0.549 on its own codebase) than on the small sample project.
- Runs as a local, single-user application.
<!-- TODO: Add anything else from docs/evaluation.md "known weaknesses" you want visitors to know. -->

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
