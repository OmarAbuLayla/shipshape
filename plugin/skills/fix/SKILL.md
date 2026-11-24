---
name: fix
description: Fix problems Shipshape found in a Python project, applying only edits that Shipshape has verified. Use when the user asks to fix Shipshape findings, clean up a project after a Shipshape review, or improve a project's grade.
argument-hint: "[findings to fix, e.g. 'leakage and seeds', 'top 3', or 'all']"
---

# Fix findings with verified edits

Shipshape's `verify_fix` tool applies your edits in memory and checks them: every edited file
still parses, the finding is gone from every place it was reported in the edited files, and no
other check reports more problems there. It never changes files. You apply an edit only after it
passed. That guarantee is the point of this skill: never skip it.

1. **Make sure changes can be undone.** Run `git status` in the project. If the folder is not a
   git repository, or has uncommitted changes, say so and ask whether to continue (suggest
   committing first). Do not proceed without an answer.
2. **Know the current state.** If there is no Shipshape scan of this project earlier in the
   conversation, call `scan` now.
3. **Choose what to fix.** Take the findings the user named in `$ARGUMENTS`; if they named none,
   ask. For "top N" or "all", rank like this:
   - Severity first (critical, then major, then minor), in the order `scan` lists them.
   - Within a severity, prefer findings that make the code crash or give wrong results over
     style, and real code over dead copies (code that nothing imports).
   - Only findings with a local code fix count: skip notebook-only findings and findings whose
     fix is a design decision (where configuration should live, splitting modules, whether a
     missing file should stop the run, deleting folders). List those as left for the user, and
     fix them only if the user asks for that specific finding.
   - Data leakage is fixable when the right split is clear from the code (for example, a
     patient or subject id is already there). Fix it, and say plainly that the reported score
     will likely drop and why that lower score is the honest one.
4. **For each finding, one at a time:**
   - Read the flagged code and write the smallest edits that fix every place the finding is
     reported in the files you touch. An edit has a `path` relative to the project and a
     `replace` text, plus either an exact `search` text (unique in the current file) or whole
     line numbers `line` and `end_line` as the file is on disk now.
   - Call `verify_fix` with the project path, the finding's check id and the edits.
   - If it says **PASSED**, apply exactly the same edits with your Edit tool. If it adds that
     the problem is still reported elsewhere (for example in a copied folder), tell the user
     where; do not silently leave it out.
   - If it says **REJECTED**, read the reason and revise at most twice. If it still fails, do not
     apply anything for this finding: explain the fix in words instead.
   - Findings in notebooks (`[cell N]`, where N counts code cells only, from 1) cannot be
     verified. Describe the change; do not edit the notebook unless the user asks, and then say
     it was not verified.
5. **Scan again** and report the grade and scores before and after, which findings were fixed,
   and which were left and why. The scan explains how each score was computed; use it when a
   score moves more or less than the user would expect.
6. **Remind the user to run their tests.** Shipshape never runs code, so a verified fix is valid
   and removes the problem without new detectable ones, but it cannot prove the program still
   behaves the same. If the project has tests, offer to run them.

**Secrets.** For a hard-coded secret, replace the line by its number (`line`) so the value is
never quoted in your edits or messages, read it from an environment variable instead, and tell
the user to rotate the key, since it may already be in git history. Never print secret values;
refer to them by file and line.
