---
id: rag-ai-assistant
type: project
title: "RAG AI Assistant: Chat with Your Documents"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [rag, llm, documents, chromadb]
project_status: completed
technologies: [Python, LangChain, ChromaDB, OpenAI Embeddings, OpenRouter, FastAPI, React, TypeScript, Vite, Tailwind CSS]
repository_url: https://github.com/AbdullahThweib2004/RAG-AI-Assistant
demo_url: null
featured: false
order: 5
---
# Project: RAG AI Assistant

## Project ID
See frontmatter.

## Status
See frontmatter.

## One-line summary
A retrieval-augmented generation application that lets users chat with uploaded PDF documents and get context-aware answers with source citations.

## Problem
Finding and combining information spread across several long documents is slow. The assistant answers questions directly from the documents and shows where each answer came from.

## Target users
Anyone who needs to ask questions across a set of documents.

## Abdullah's contribution
<!-- TODO: Solo project? Was this your first RAG project? What did you learn from it that you used later in the AI Developer Assistant? -->

## Architecture
An ingestion script loads the documents, splits them, embeds them and stores the vectors in ChromaDB. A FastAPI backend retrieves the relevant passages and asks an LLM through OpenRouter to answer from them. A React and TypeScript frontend provides the chat interface.

## Technologies
See frontmatter.

## Data sources
Sample documents included with the project, about AI search, SEO, GEO and AIO.

## Key implementation details
- Multi-document querying across several PDFs.
- Synthesis that combines information from different documents.
- A comparison mode that compares concepts even when the documents contain no comparison table.
- Source citations for every answer.
- Detects unrelated questions and says the topic is not covered instead of inventing an answer.

## Challenges and trade-offs
<!-- TODO: What was hard here? For example chunk size, comparison questions, or keeping the model from answering outside the documents. -->

## Results (only verified results)
<!-- TODO: Any measured results? If none, leave this section out or write "No formal evaluation yet." -->

## Limitations
<!-- TODO: Known limitations? -->

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
