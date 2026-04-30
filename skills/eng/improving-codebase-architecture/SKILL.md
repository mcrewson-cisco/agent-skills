---
name: improving-codebase-architecture
description: Use when a codebase is hard to navigate or test because one concept is split across shallow, tightly coupled modules, and you need concrete refactor candidates with a recommended first target.
---

# Improving Codebase Architecture

## Overview

Find architectural friction worth fixing before design work starts. Focus on clusters that should become deeper modules: smaller interfaces hiding cohesive behavior.

This skill does not design the new interface, write the spec, or produce an implementation plan. It identifies candidates, recommends one to pursue first, and hands off to `brainstorming`.

## When to Use

Use this skill when:
- Understanding one behavior requires bouncing between several small files.
- A concept is split across helpers, orchestrators, and adapters, and callers know too much about the sequence.
- Unit tests pass on isolated helpers, but bugs still show up in the seams between modules.
- Several files share flags, types, or state transitions for one concept.
- The user wants architectural cleanup, refactor candidates, or improved testability before committing to a design.

Do not use this skill when:
- The user already chose the refactor and wants interface design or a spec. Use `brainstorming`.
- The main problem is a concrete bug, flaky test, or regression. Use `systematic-debugging`.
- The task is implementation planning after an approved design. Use `writing-plans`.
- The task is review feedback on an existing change. Use `receiving-code-review`.

## Quick Reference

| Signal | What it usually means | Good candidate? |
| --- | --- | --- |
| One caller wires 3-5 helpers in a fixed order | The caller owns behavior it should not know | Yes |
| Shared flags or types appear across multiple modules for one concept | The boundary is too shallow | Yes |
| Tests mostly mock neighbors instead of checking end-to-end behavior | The seam is carrying too much logic | Yes |
| Large file with unrelated helpers | File-size problem, not necessarily an architectural one | Maybe not |
| Similar cloud or host-lifecycle code appears in two modules but serves different operational contracts | Possible duplication, not automatically one architectural concept | Maybe not |
| Pure naming or formatting inconsistency | Style issue, not a module boundary issue | No |

## Dependency Check

Classify each candidate before recommending it:

| Dependency shape | Typical recommendation |
| --- | --- |
| In-process | Merge behavior behind one boundary and test directly |
| Local stand-in available | Deepen the module and test against the stand-in |
| Remote but owned | Hide transport behind a local port or adapter and test with an in-memory implementation |
| True external | Keep ownership at the local orchestration boundary and mock only the external edge |

The goal is not "delete all unit tests." Replace redundant seam tests only after boundary tests cover the behavior that matters.

## Process

### 1. Explore inline first

Inspect the codebase directly. Follow one concept across files and note where understanding or testing breaks down.

Default to inline exploration. Only use delegated or parallel agent exploration if the user explicitly asks for it and the environment supports it.

Before final ranking, inspect at least one related test file for each serious candidate. Use the tests to distinguish a true boundary problem from a file-size or style problem.

### 2. Build 2-4 concrete candidates

For each candidate, capture:
1. **Cluster**: the files, modules, or concepts involved
2. **Evidence**: at least two concrete code references
   - one caller, orchestrator, or boundary-owning seam
   - one downstream module seam or test seam
3. **Why coupled**: what concept is split across boundaries
4. **Dependency shape**: choose one from the dependency check above
5. **Boundary test opportunity**: what behavior could move to one public interface
6. **Payoff**: what gets simpler for callers, tests, and future changes
7. **Risk**: migration cost, ownership boundaries, or unclear responsibilities

### 3. Rank the candidates

Score each candidate qualitatively:
- **Cohesion gain**: low, medium, or high
- **Boundary-test gain**: low, medium, or high
- **Migration risk**: low, medium, or high
- **Confidence**: low, medium, or high based on the quality of the evidence you found

Prefer the candidate with the best payoff-to-risk ratio:
- Strong cohesion gain
- Strong boundary-test gain
- Clear local ownership
- Risk contained to one real concept rather than broad cleanup

Do not recommend the most ambitious candidate just because it is interesting.

If you cannot find a candidate with concrete evidence and a plausible boundary-test story, say so explicitly and stop. Do not manufacture an architectural refactor out of file size, naming churn, or vague cleanup instincts.

### 4. Recommend one candidate

Present:
- A numbered list of candidates
- Your recommended candidate to pursue first
- A short reasoned argument for that recommendation
- A short reasoned argument for why the runner-up is not the first move

Keep the recommendation focused on why this is the next architectural problem to solve, not on the final interface design.

### 5. Frame the handoff

For the recommended candidate, provide a brief problem frame:
- What concept should be owned in one place
- What callers should stop knowing
- What constraints the future design must preserve
- Which existing tests may become redundant once boundary coverage exists
- Which questions `brainstorming` must answer before a spec is written

Then hand off to `brainstorming` to design the refactor and write the spec. After the spec is approved, use `writing-plans`.

## Output Format

Use this structure:

```markdown
1. Candidate: <short name>
   Cluster: <files or modules>
   Evidence:
   - Caller seam: <code reference + why it owns too much>
   - Downstream seam or test seam: <code reference + why it confirms the split concept>
   Dependency shape: <in-process / stand-in / owned remote / true external>
   Boundary test opportunity: <behavior to test at one public interface>
   Cohesion gain: <low / medium / high>
   Boundary-test gain: <low / medium / high>
   Migration risk: <low / medium / high>
   Confidence: <low / medium / high>
   Payoff: <what gets simpler>
   Risk: <what could make this expensive or wrong>

Recommended next move: <candidate>
Why first: <2-4 sentences>
Why not the runner-up: <1-3 sentences>

Problem frame for brainstorming:
- Own: <core responsibility>
- Hide: <sequencing, state, transport, flags, etc.>
- Preserve: <constraints>
- Test shift: <which redundant tests could be replaced later>
- Questions for brainstorming:
  - <question 1>
  - <question 2>
```

If there is no strong candidate, use this instead:

```markdown
No strong architecture candidate yet.

Why not:
- <what evidence was missing>
- <why the observed issues look like file-size, style, or local cleanup problems instead>

Next move:
- <what to inspect next, or which other skill to use>
```

## Common Mistakes

- Treating "large file" as proof of an architectural problem. Look for one concept split across seams, not just file size.
- Skipping tests while evaluating candidates. If you did not inspect at least one related test seam, your ranking is too weak.
- Designing the new interface too early. This skill chooses what to solve first; `brainstorming` decides how.
- Recommending broad cleanup with vague payoff. Stay anchored to a concrete concept and boundary.
- Deleting existing tests before replacement boundary coverage exists.
- Treating parallel-looking modules as one concept without checking whether they serve genuinely different contracts.
- Using this skill to justify unrelated refactors while already touching nearby code.
