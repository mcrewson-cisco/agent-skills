# Engineering Skillpack

`skills/eng` is the process layer for this repository. Where the domain-specific skillpacks teach an agent how to operate a particular system, this pack teaches the agent how to conduct engineering work itself: how to orient, design, plan, isolate, implement, debug, review, verify, and finish work without drifting into improvised shortcuts.

The point of this pack is not to restate generic software advice. Its purpose is to encode working discipline for agentic development so the output is deliberate, inspectable, and repeatable. The skills here are opinionated because they are trying to prevent failure modes that show up constantly in real sessions: jumping into code before understanding the task, patching symptoms instead of root causes, skipping verification, or treating review as ceremony instead of technical evaluation.

## What This Pack Covers

This skillpack spans the full lifecycle of engineering work:

- orientation before action
- brainstorming and design before implementation
- explicit plans before multi-step execution
- isolated workspaces when changes need separation
- disciplined implementation and debugging workflows
- review loops that evaluate correctness, not just style
- verification before claiming success
- intentional branch completion and handoff

Read as a whole, the pack describes a workflow system. Read skill-by-skill, it provides focused guidance for the moment you are in.

## The Role Of Each Skill

- `using-eng`: the entry point. It forces skill discovery and prevents agents from skipping relevant guidance just because a task looks simple.
- `brainstorming`: turns an idea or request into a reviewed design before implementation starts.
- `writing-plans`: converts approved requirements or specs into explicit implementation plans.
- `using-git-worktrees`: creates clean isolation when work should not happen directly on the current branch or workspace.
- `test-driven-development`: establishes behavior-first implementation discipline for features, fixes, and refactors.
- `systematic-debugging`: enforces root-cause analysis instead of random patching when behavior is broken or flaky.
- `dispatching-parallel-agents`: helps split independent work across multiple agents without mixing concerns.
- `subagent-driven-development`: coordinates plan execution through fresh subagents, with structured review between tasks.
- `executing-plans`: handles plan execution in a more direct single-session workflow when that is the right fit.
- `requesting-code-review`: creates deliberate review checkpoints before defects compound.
- `receiving-code-review`: evaluates review feedback technically instead of accepting or rejecting it reflexively.
- `verification-before-completion`: requires evidence before claiming work is done or fixed.
- `finishing-a-development-branch`: closes the loop by guiding merge, PR, or cleanup choices once implementation is complete.
- `writing-skills`: applies the same engineering rigor to the creation and refinement of skills themselves.

## How To Use This Pack

Start with the specific skill that matches the current phase of work, but treat the pack as connected guidance rather than isolated documents. For example, a typical path might move from `using-eng` to `brainstorming`, then to `writing-plans`, then into `test-driven-development` or `systematic-debugging`, followed by review and verification skills before branch completion.

Not every task uses every skill. The value of the pack is that it makes those transitions explicit. It gives agents a structured way to move from uncertainty to finished work without collapsing everything into ad hoc terminal behavior.

## When To Reach For `skills/eng`

Use this pack when the hard part of the task is engineering judgment and execution quality:

- shaping ambiguous requests into a design
- planning multi-step implementation work
- making code changes safely
- debugging failing systems or tests
- reviewing or responding to review feedback
- deciding whether work is actually done
- authoring or refining the skills in this repository

Reach for a domain-specific pack instead when the main problem is operational knowledge about a tool or platform such as Jira, Confluence, Webex, CHIM, PagerDuty, GitHub CLI, or 1Password. In practice, many real tasks use both: an engineering skill for process and a domain skill for system-specific commands or constraints.

## Read Me As A Map, Not A Substitute

This README explains the purpose of the `eng` skillpack and how the pieces fit together. The actual operating rules live in the individual `SKILL.md` files and their supporting prompts and references. If this file gives you the map, those files provide the route.
