# Agent Skills

This repository is a library of reusable skills for agentic work. Each skill is a focused piece of operating guidance: when it applies, how it should be used, and what patterns or constraints matter when an agent is doing real work in a terminal, codebase, or connected tool environment.

The repository is organized as a set of skillpacks rather than a single monolithic guide. That separation is intentional. Some skills are about engineering process and execution discipline. Others are domain packs for specific systems such as Jira, Confluence, Webex, CHIM, PagerDuty, GitHub CLI, or 1Password. Keeping them separate makes it easier to compose the right guidance for the job without turning every session into a giant, generic handbook.

## What Lives Here

Each skill lives in its own directory under `skills/`. The authoritative entry point is always `SKILL.md`. Supporting files sit beside it when the skill needs extra prompts, reference material, examples, or helper scripts.

Typical structure:

```text
skills/
  <skill-name>/
    SKILL.md
    references...
    scripts...
```

The `SKILL.md` file explains the triggering conditions for the skill and the workflow it expects the agent to follow. Supporting files exist to keep the main skill readable while still giving it access to detailed prompts, templates, and references when needed.

## Skill Collections

This repository currently contains:

- `skills/eng/`: the engineering process skillpack. It covers the operating discipline around planning, implementation, debugging, review, verification, and branch completion.
- `skills/chim/`: workflows for incident and change analysis through the local CHIM helper.
- `skills/confluence/`: CLI-first Confluence workflows for reading, exporting, and working with page data.
- `skills/gh-cli/`: GitHub CLI reference and operating guidance.
- `skills/jira/`: Jira workflows for issue, sprint, and project work.
- `skills/op/`: minimal-access 1Password retrieval workflows.
- `skills/pagerduty/`: incident and on-call analysis through the local PagerDuty helper.
- `skills/webex/`: Webex room, message, and participant workflows.

## How To Read This Repo

Use the top-level layout to find the relevant skill domain, then read the specific `SKILL.md` for the task at hand. The README files are orientation documents. The skill files are the operational source of truth.

If you are trying to understand how the repository thinks about engineering work in particular, start with [`skills/eng/README.md`](/Users/mcrewson/work/mcrewson/agent-skills/skills/eng/README.md). That pack is the process backbone for the rest of the collection: it defines how work should be scoped, planned, implemented, reviewed, verified, and closed out.

## Why `skills/eng` Matters

Most domain skills answer questions like "how do I use this system safely and effectively?" The engineering pack answers a different question: "how should an agent conduct software work so the outcome is disciplined, reviewable, and reliable?"

That distinction is why `skills/eng` exists as a dedicated skillpack. It is the shared process layer that can sit underneath work in any domain, whether the task is writing code, debugging a failure, drafting a plan, or authoring new skills.
