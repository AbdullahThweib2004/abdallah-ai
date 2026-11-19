# Requirements

Source: the project specification (kept private), §4, §5.

Priorities: **P0** = essential for the first public release, **P1** = important, **P2** = future enhancement.

## Functional requirements

| ID | Requirement | Priority | Acceptance summary |
|---|---|---|---|
| FR-01 | Display Abdallah's avatar | P0 | Avatar and welcome experience render on supported browsers. See deviation D-2: the avatar is a stylized 3D robot, not a likeness of Abdallah. |
| FR-02 | Text conversation | P0 | Visitor can send a message and receive an AI response. |
| FR-03 | Knowledge-grounded answers | P0 | Answers use approved profile and project information. |
| FR-04 | Arabic and English | P0 | Text conversations work in both languages. |
| FR-05 | Voice input / STT | P1 | Visitor can speak and receive a transcription. |
| FR-06 | Voice output / TTS | P1 | AI response is played as audio. |
| FR-07 | Abdallah voice identity | P1 | ~~Authorized voice model produces a sufficiently similar voice.~~ Not pursued, see deviation D-1. |
| FR-08 | Animated talking avatar | P1 | Mouth motion is acceptably synchronized with generated speech. Met by the robot's equalizer mouth, driven by the real TTS audio level (D-2). |
| FR-09 | Project display actions | P0 | AI can request a permitted project card to be shown. |
| FR-10 | Session context | P0 | Follow-up questions refer to earlier turns in the same session. |
| FR-11 | Interruption | P2 | Visitor can stop current speech and begin a new turn. |
| FR-12 | Contact links | P0 | Public GitHub, LinkedIn, and contact links are available. |
| FR-13 | Fallback experience | P0 | Provider failures do not crash the whole site. |
| FR-14 | Responsive layout | P0 | Core experience works on desktop and mobile. |

## Documented deviations from the spec

Product decisions by Abdallah that knowingly depart from the original specification. Recorded 2026-11-18 (build step 9).

| ID | Spec | Decision | Why / consequence |
|---|---|---|---|
| D-1 | §4 FR-07, build step 8: clone Abdallah's authorized voice. | **Skipped.** The assistant keeps the stock ElevenLabs voice ("Chris"). | No voice samples are collected or stored, no cloning cost. The assistant still never claims to be Abdallah; FR-07 is not pursued. |
| D-2 | Confirmed decision "realistic avatar based on Abdallah's real appearance"; build step 9 "realistic avatar with lip sync". | **An original, stylized 3D robot head** built in code (three.js + react-three-fiber in the browser), not a human face and not a paid avatar service. | Free to run (no per-minute cost, no avatar provider, no backend avatar adapter), no likeness or authorized-media concerns. "Lip sync" becomes an equalizer mouth driven by the real TTS audio level. An authorized photo (`frontend/public/avatar/abdallah.jpg`, if present) is shown on `/about` only. |

## Non-functional requirements

| Area | Requirement / target |
|---|---|
| Performance | Keep the first page lightweight. Measure end-to-end voice latency and optimize each stage. |
| Availability | The site stays usable in text mode if voice or avatar services fail. |
| Scalability | Separate frontend, orchestration, voice and avatar integrations so they can scale independently. |
| Maintainability | Typed API contracts, modular adapters, environment configuration, automated tests. |
| Accessibility | Text alternatives, keyboard-accessible controls, visible focus states, captions/transcripts where practical. |
| Privacy | Do not store raw audio or visitor personal information by default. |
| Security | Keep provider credentials server-side, validate actions, apply rate limits and request-size limits. |
| Compatibility | Test current desktop and mobile versions of major browsers. |
| Cost | Track API usage and set per-session and monthly spending limits. |

## Initial release acceptance checklist (§15.4)

- [ ] The visitor can start a session and use text chat.
- [ ] The AI answers profile questions using verified information.
- [ ] The AI can accurately explain at least three documented projects.
- [ ] Arabic and English text conversations work.
- [ ] Conversation context is preserved within a session.
- [ ] The interface can display a selected project through a validated action.
- [ ] Voice input and output work in the selected supported browsers.
- [ ] The avatar's speech is acceptably synchronized with audio.
- [ ] Provider failures do not make the whole site unusable.
- [ ] No API secret is exposed in frontend code or network responses.
- [ ] The site is usable on desktop and mobile.
