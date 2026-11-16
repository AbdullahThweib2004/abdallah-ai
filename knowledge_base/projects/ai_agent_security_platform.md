---
id: ai-agent-security-platform
type: project
title: "AI Agent Security & Control Platform"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [ai-agents, security, a2a, forensics, graph]
project_status: completed
technologies: [Python, FastAPI, Pydantic, PostgreSQL, SQLAlchemy, Alembic, Neo4j, React, Vite, Tailwind CSS, Docker, GitHub Actions]
repository_url: https://github.com/AbdullahThweib2004/ai-agent-security-platform
demo_url: null
featured: true
order: 3
---
# Project: AI Agent Security & Control Platform

## Project ID
See frontmatter.

## Status
See frontmatter. All five planned capabilities are complete and verified against live data and on CI.

## One-line summary
A security layer that monitors and governs autonomous AI agents inside an organization: their actions, tool calls, delegations, and communication with other agents.

## Problem
As organizations let AI agents act on their behalf, they need to see what each agent did, control how much authority passes when one agent hands work to another, decide which agents should talk at all, and stop an agent that has gone wrong.

## Target users
Security and platform teams that operate autonomous AI agents.

## Abdallah's contribution
Abdallah designed and built the whole project on his own.

## Architecture
Agents report every action as an event to a FastAPI service. Each event is stored in PostgreSQL as a durable event log and projected into Neo4j as a graph of entities and relationships. A React dashboard shows agents, the behavior graph, alerts and forensic timelines. The whole stack runs with Docker Compose.

## Technologies
See frontmatter.

## Data sources
Simulated agent events from a seed simulator: a banking scenario with injected anomalies, including an external attacker agent.

## Key implementation details
Five capabilities:
1. Agent Behavior Graph: every agent action becomes an event, projected into a graph that can be explored and baselined.
2. Agent Forensics: reconstructs the full causal chain of an incident by following parent and child event links, with each policy layer's verdict attached.
3. Delegation Security: a delegate receives only the least privilege the task needs. A delegator can never pass on authority it does not hold, and sensitive categories such as customer data, money movement and admin control are never granted automatically.
4. Agent-to-agent (A2A) Security: decides whether two agents should interact at all, based on identity and trust levels, before looking at what is being asked.
5. Incident Response: when independent layers agree that an agent has gone wrong, it is contained automatically. Only a named operator can lift containment.

Other design points:
- What an agent reports about its own action is stored unchanged, and the platform's own verdict is stored separately, because an agent cannot be trusted to grade itself.
- Anomaly detection is rule-based (no machine learning): new counterparties, unusual values, and never-before-used permissions.
- Baselines exclude blocked and suspicious events, so an agent cannot widen its own idea of "normal" one anomaly at a time.
- The service refuses to start against a database at the wrong schema revision, and a reconciler repairs events that reached Postgres but not the graph.

## Challenges and trade-offs
- Avoiding false alarms: containment needs corroboration across at least two independent layers (or two high-severity alerts) within 24 hours. In the seeded data this fires on exactly one agent-day: the actual attacker.
- Cold start: agents with fewer than three clean events are not judged, to avoid alert storms. New malicious agents are still caught from the other side, when an established agent contacts them.
- Automatic containment, operator-only release: a wrong suspension is visible and recoverable, while a wrong automatic release would let a compromised agent act silently.

## Results (only verified results)
- 502 tests with 99% statement coverage, run against real PostgreSQL and Neo4j instead of mocks.
- The test suite is mutation-checked: deliberately breaking key rules makes it fail.
- CI on every push and pull request (lint, formatting, full test suite, frontend build). Each CI gate was verified by breaking it on purpose.

## Limitations
- The platform observes events after the fact. It is not in the request path, so its decisions are records rather than real-time blocking.
- Detection is rule-based only.
- New agents get a grace period before they are judged.
- Tested on simulated data, not a live production agent fleet.

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
