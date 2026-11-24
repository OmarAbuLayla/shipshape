---
name: fix
description: Fix problems Shipshape found in a Python project, applying only edits that Shipshape has verified. Use when the user asks to fix Shipshape findings, clean up a project after a Shipshape review, or improve a project's grade.
argument-hint: "[findings to fix, e.g. 'leakage and seeds', or 'all']"
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
   conversation, call `scan` now. Pick the findings from `$ARGUMENTS` or ask which to fix; if the
   user says "all", start with the most severe and leave findings that need a human decision
   (secrets, data leakage design, structure) for last and confirm those.
3. **For each finding, one at a time:**
   - Read the flagged code and write the smallest edits that fix every place the finding is
     reported in the files you touch. Each edit is an exact `search` text (unique in the file,
     copied from the current file) and its `replace` text, with a path relative to the project.
   - Call `verify_fix` with the project path, the finding's check id and the edits.
   - If it says **PASSED**, apply exactly the same edits with your Edit tool.
   - If it says **REJECTED**, read the reason and revise at most twice. If it still fails, do not
     apply anything for this finding: explain the fix in words instead.
   - Findings in notebooks (`[cell N]`) cannot be verified. Describe the change; do not edit the
     notebook unless the user asks, and then say it was not verified.
4. **Scan again** and report the grade and scores before and after, which findings were fixed,
   and which were left and why.
5. **Remind the user to run their tests.** Shipshape never runs code, so a verified fix is valid
   and removes the problem without new detectable ones, but it cannot prove the program still
   behaves the same. If the project has tests, offer to run them.

Special cases: for a hard-coded secret, move it to an environment variable and tell the user to
rotate the key, since it may already be in git history. Never print secret values.
