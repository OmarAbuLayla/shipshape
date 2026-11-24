---
name: lesson
description: Teach the software-engineering concept behind a Shipshape finding (data leakage, random seeds, mutable defaults, closures, and 21 more) with a before and after. Use when the user asks why something Shipshape flagged matters, or wants to learn a concept like these.
argument-hint: "[concept, lesson name or check id]"
---

# Teach a concept

1. Call the Shipshape `lesson` tool with `$ARGUMENTS` (a lesson name such as `data-leakage`, a
   concept, or a check id such as `lint.mutable-default`). With no argument, it lists all lessons:
   show them briefly and ask which one.
2. Present the lesson in your own words, keeping its structure: the idea, a before and
   after, why engineers care, how Shipshape spots it (including what it cannot detect), and the
   further reading.
3. If this conversation has scanned a project with this problem, connect the lesson to the
   user's own code: show where it happens there and what the "after" would look like.
