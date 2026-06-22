# Workflow Patterns

## Sequential Workflows

For complex tasks, break operations into clear, sequential steps. Provide an overview at the beginning:

```markdown
Filling a PDF form involves these steps:

1. Analyze the form (run analyze_form.py)
2. Create field mapping (edit fields.json)
3. Validate mapping (run validate_fields.py)
4. Fill the form (run fill_form.py)
5. Verify output (run verify_output.py)
```

---

## Conditional Workflows

For tasks with branching logic, guide Claude through decision points:

```markdown
1. Determine the modification type:
   **Creating new content?** → Follow "Creation workflow" below
   **Editing existing content?** → Follow "Editing workflow" below

2. Creation workflow: [steps]
3. Editing workflow: [steps]
```

---

## Validation Gates

Add checkpoints before proceeding to next steps:

```markdown
# Step 2: Validate Before Processing

CRITICAL: Before calling create_project, verify:
- Project name is non-empty
- At least one team member assigned
- Start date is not in the past

If any check fails:
- Report the specific failure to user
- Do NOT proceed to Step 3
```

---

## Error Recovery

Include rollback and retry instructions:

```markdown
# Error Handling

If Step 3 fails:
1. Log the error details
2. Attempt cleanup of partial resources
3. Report to user with specific error
4. Suggest corrective action

Rollback sequence:
1. Delete created tasks (if any)
2. Remove project entry
3. Restore original state
```

---

## Progress Communication

Keep users informed during long workflows:

```markdown
# User Communication

After each major step, briefly report:
- What was completed
- What's happening next
- Estimated remaining steps

Example: "✓ Project created. Now creating 5 tasks... (Step 2 of 4)"
```

---

## For Advanced Patterns

See `references/advanced-patterns.md` for:
- Sequential Workflow Orchestration
- Multi-MCP Coordination
- Iterative Refinement
- Context-Aware Tool Selection
- Domain-Specific Intelligence
