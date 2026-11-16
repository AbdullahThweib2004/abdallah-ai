---
id: momentum
type: project
title: "Momentum: LinkedIn Content Assistant"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [nextjs, supabase, content, productivity]
project_status: in_progress
technologies: [Next.js, TypeScript, Tailwind CSS, shadcn/ui, Supabase, PostgreSQL, Recharts, Vercel]
repository_url: https://github.com/AbdullahThweib2004/Momentum
demo_url: null
featured: false
order: 6
---
# Project: Momentum

## Project ID
See frontmatter.

## Status
See frontmatter. The application is built; AI draft generation is still a placeholder.

## One-line summary
A personal LinkedIn content assistant that tracks the topics you care about, generates post drafts on them, and lets you review, edit and mark posts as published, without ever posting for you.

## Problem
Posting consistently on LinkedIn is hard. Momentum helps a person stay consistent by keeping their topics, drafts and publishing history in one place.

## Target users
Professionals who want to post regularly on LinkedIn.

## Abdullah's contribution
<!-- TODO: Solo project? Did you build it for yourself? -->

## Architecture
A Next.js App Router application in TypeScript, with Supabase for the database and authentication. Data access reads from Supabase and falls back to an in-memory mock dataset when Supabase is not configured. Deploy-ready for Vercel.

## Technologies
See frontmatter.

## Data sources
The user's own interests, drafts and engagement logs. A demo mode ships with mock data.

## Key implementation details
- Dashboard with pending drafts, weekly and monthly publishing counts, top interests and a 30-day activity chart.
- Drafts: generate, review, edit, approve or reject, schedule, and mark as published, with a LinkedIn-style live preview.
- Interests with weights: publishing about a topic raises its weight for future generation, through a database trigger.
- Engagement log for posts the user liked, commented on or shared.
- History with topic distribution and posting-frequency analytics.
- Settings for the user's writing voice and three to five content pillars.
- Row Level Security scoped per user, so the schema is multi-user ready.
- Runs fully populated with no configuration in demo mode.

## Challenges and trade-offs
- The user always publishes on LinkedIn manually. Momentum never posts automatically.
<!-- TODO: Anything else hard or interesting? -->

## Results (only verified results)
<!-- TODO: Do you use it yourself? Any results? Otherwise remove this TODO and leave the section empty. -->

## Limitations
- AI draft generation currently returns mock content. The function is ready to be connected to an AI provider.

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
