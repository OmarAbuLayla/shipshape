---
name: review
description: Review a Python project the way a careful senior engineer would, using Shipshape's static checks, grade and lessons. Use when the user asks to review, audit or grade a Python project or research code, asks what an engineer would object to, or wants to know if AI-written (vibe-coded) code is ready to share.
argument-hint: "[project folder]"
---

# Review a project with Shipshape

Shipshape finds problems with static checks (it never runs the code) and grades six dimensions:
correctness, structure, reproducibility, readability, testing and security. Its findings are
deterministic; your job is to explain them in the user's own code and to teach the idea behind
them. This skill only reads: do not edit files here.

1. **Pick the folder.** Use `$ARGUMENTS` if given, otherwise the current working directory.
   Pass an absolute path to the tools.
2. **Scan.** Call the Shipshape `scan` tool. If the project has many findings, the first scan
   is enough; do not raise `max_findings` unless the user wants everything.
3. **Summarise first.** Give the grade, the weakest dimensions and the number of findings in
   two or three sentences. Say that the grade is a rough guide.
4. **Explain the most important findings**, at most five, most severe first. For each one, read
   the flagged lines with your own tools, then say in plain language what is going on in *this*
   code, why an engineer cares, and what the fix would look like. Be concrete: name the file,
   the function and the variable. Group repeated findings (e.g. the same problem in a copied
   folder) instead of listing them twice.
5. **Be honest about uncertainty.** Some checks are phrased as questions (data leakage, for
   example): say what would make it a real problem and what would make it fine. If you notice a
   problem Shipshape did not report (leakage through preprocessing, patient data sent to an
   outside service, dead copies of code), mention it separately and say it was not one of
   Shipshape's findings.
   In machine-learning code, always check two kinds of leakage Shipshape cannot see:
   preprocessing statistics (scalers, quantiles, medians, imputers, feature selection)
   computed on all rows before the train/test split, and hand-made splits in notebooks or
   scripts (shuffled indices sliced into train and test) that ignore subjects or patients.
6. **Point onwards.** Name the lesson for one or two concepts the user may not know (they can
   run `/shipshape:lesson <name>`), offer `/shipshape:fix` for the findings that have a clear
   fix, and offer the `map` tool if the user wants to see the project's structure.

Never print the value of a secret Shipshape found; refer to it by file and line.
