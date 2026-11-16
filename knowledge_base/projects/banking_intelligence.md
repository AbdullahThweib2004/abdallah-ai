---
id: banking-intelligence
type: project
title: "AI-Powered Banking Intelligence Platform"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [banking, rag, llm, ocr, credit-risk, graduation-project]
project_status: in_progress
technologies: [React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Supabase, PostgreSQL, pgvector, Supabase Edge Functions, FastAPI, Tesseract OCR, OpenCV, WeasyPrint, OpenRouter]
repository_url: https://github.com/AbdullahThweib2004/banking-intelligence-platform
demo_url: null
featured: true
order: 2
---
# Project: AI-Powered Banking Intelligence Platform

## Project ID
See frontmatter.

## Status
See frontmatter. Nearly complete: all core features are built; the remaining work is security hardening and deployment. Built as an academic graduation project, a realistic demo rather than a production banking system.

## One-line summary
A bilingual English and Arabic web platform that simulates the internal tools of a Bank of Palestine branch: AI credit-risk scoring, ID-photo account opening with OCR, an approvals workflow, and a policy-grounded RAG assistant.

## Problem
Branch staff juggle disconnected tools and manual steps: entering credit applications, retyping a customer's ID to open an account, tracking which loan applications are waiting for review, and searching PDF handbooks for policy answers. The platform brings these workflows into one role-aware dashboard.

## Target users
Three internal bank roles: branch employees, branch managers, and the risk department.

## Abdallah's contribution
Abdallah designed and built the whole platform on his own as his graduation project.

It is an independent academic project. It is not related to his training at Bank of Palestine, and it was not built for, used by, or endorsed by the bank. The bank's name is used only to give the demo a realistic scenario.

## Architecture
A React single-page application backed by Supabase: PostgreSQL with Row Level Security, Auth, Realtime, Storage, and three Edge Functions (AI credit assessment, policy semantic search, and privileged user administration). A separate FastAPI microservice handles OCR of ID photos and PDF generation for the account-opening flow. LLM calls and embeddings go through OpenRouter.

## Technologies
See frontmatter.

## Data sources
Seeded demo data only, including ten demo customers. The AI assistant's knowledge base is three policy documents that Abdallah wrote himself: a loan policy, an account-opening policy, and customer service guidelines. They are modelled on how banks generally write such policies and are not real Bank of Palestine documents. No real customer data is used.

## Key implementation details
- AI credit scoring: the LLM returns a structured JSON result with score, risk category, confidence, a plain-language summary, ranked contributing factors and a recommended action. If the AI call fails, the app falls back to a deterministic, unit-tested scoring model with the same output shape.
- Account opening: a four-step wizard uploads an ID photo, extracts fields with Tesseract and OpenCV (regex parsing with an optional LLM fallback), collects two signatures, and generates a bilingual two-copy PDF form.
- RAG assistant: answers only from the bank's policy documents, cites the source policy section, detects English or Arabic, and refuses out-of-scope questions. It uses pgvector semantic search, with an in-browser keyword search fallback if the vector store is unreachable.
- Access control enforced in the database: Row Level Security policies for the three roles, and an append-only audit log written by Postgres triggers so it cannot be skipped by a UI bug.
- Explainability: every credit score is saved with its explanation, and a custom Help Mode lets users click any UI element to see what it does.
- Full English and Arabic interface with right-to-left layout.

## Challenges and trade-offs
- The LLM provider was unreliable during development (rate limits and credits), which led to the AI-first design with an algorithmic fallback.
- Fixed a React infinite render loop in the Help Mode by keying target registration on a content hash and memoizing the context value.
- Role checks read the role from the login token to avoid recursive database policies. The trade-off is that a role change only takes effect after the user signs in again.

## Results (only verified results)
- A self-authored QA package: 96 documented test cases, 9 automated unit tests (all passing), and an overall verdict of "conditional pass, academic and demo ready".
- The production build passes.

## Limitations
- An academic demo, not cleared for a bank pilot or production.
- Known open issues at the last review: the OCR service trusts a role header sent by the client instead of verifying the user's session, role changes need a re-login, and there are no end-to-end tests or CI yet.


## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
