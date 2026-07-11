---
name: minimal-change-implement
description: Apply the smallest safe implementation change for this repository without unrelated refactors or architecture drift.
---

# Minimal Change Implement

## Purpose
Use this skill when the task is to implement an incremental product change in the current repository.

This skill exists to keep code changes small, safe, understandable, and aligned with the current architecture.

It should prevent:
- unnecessary redesign
- unrelated refactors
- contract drift
- “while I’m here” code expansion

## Use this skill when
Use this skill when:
- adding a focused backend feature
- adding a focused frontend feature
- integrating one small new layer into the current system
- patching a bug in an existing workflow
- modifying a working flow without changing overall architecture

## Do NOT use this skill when
Do NOT use this skill when:
- the task explicitly asks for a redesign
- the task is primarily architecture exploration
- the task is a large system decomposition
- the task requires a new product concept rather than an incremental implementation step

## Core rules
- Prefer the smallest safe change that moves the product forward.
- Do not refactor unrelated code.
- Do not rename fields unless explicitly instructed.
- Do not touch more files than necessary.
- Preserve existing contracts and working behavior unless the task explicitly changes them.
- Reuse current structures before introducing new abstractions.
- Avoid duplicate external API calls when the data already exists.
- Keep implementation easy to reason about.
- Do not accidentally harden the wrong product assumption just because it is convenient in the current code.
- In this repository, prefer interest-first planning flow over reintroducing hotel-first gating unless explicitly requested.

## Required working style
Before editing:
- explain the smallest correct next step
- list the exact files to change
- state assumptions clearly

After editing:
- summarize exactly what changed
- list files changed
- explain why the change is minimal and correct
- list regression risks
- provide exact local test steps

## Extra checks
- If backend schema changes, check frontend expectations.
- If frontend rendering changes, check backend field availability.
- If external API integration changes, check whether duplicate calls were introduced.
- If LLM integration is involved, preserve deterministic execution boundaries.
