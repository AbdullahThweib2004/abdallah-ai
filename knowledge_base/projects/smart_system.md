---
id: smart-system
type: project
title: "Smart System: Local AI Developer Assistant (Desktop)"
language: en
status: draft
visibility: public
last_reviewed: null
tags: [electron, desktop, developer-tools, local-ai]
project_status: completed
technologies: [Electron, React, TypeScript, Vite, node-pty, SQLite, Ollama]
repository_url: https://github.com/AbdullahThweib2004/smart-system
demo_url: null
featured: false
order: 7
---
# Project: Smart System

## Project ID
See frontmatter.

## Status
See frontmatter.

## One-line summary
A local, AI-powered desktop assistant for developers, built with Electron, that manages projects, runs a built-in terminal, detects errors automatically and generates AI prompts with full project context.

## Problem
Developers switch between many projects and tools. Smart System puts project management, a terminal, error detection and AI help in one desktop app that can work fully offline.

## Target users
Developers who work on several projects at once.

## Abdallah's contribution
Abdallah designed and built the whole project on his own.

## Architecture
An Electron desktop application with a React and TypeScript interface built with Vite. The main process provides the terminal through node-pty and local storage through SQLite, and exposes them to the interface through a preload bridge. AI features can run locally through Ollama.

## Technologies
See frontmatter.

## Data sources
The user's own local projects.

## Key implementation details
- Multi-project manager with automatic project-type detection.
- Integrated terminal (cmd or PowerShell).
- Automatic error detection from terminal output.
- Smart suggestions per project, such as adding tests, git or CI.
- AI prompt generator that includes the full project context.
- Settings for theme, language, shell and AI model.
- Works fully offline with local AI through Ollama.

## Challenges and trade-offs
- Native modules (node-pty and SQLite) failed to load because they were compiled for a different Node version than the one inside Electron. Fixed by rebuilding them for Electron automatically after every install.

## Results (only verified results)
No formal evaluation has been published for this project yet.

## Limitations
- The integrated terminal targets Windows shells (cmd and PowerShell).

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
