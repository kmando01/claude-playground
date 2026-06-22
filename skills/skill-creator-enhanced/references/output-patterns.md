# Output Patterns

Use these patterns when skills need to produce consistent, high-quality output.

## Template Pattern

Provide templates for output format. Match the level of strictness to your needs.

### For Strict Requirements

(Like API responses or data formats)

```markdown
## Report structure

ALWAYS use this exact template structure:

# [Analysis Title]

## Executive summary
[One-paragraph overview of key findings]

## Key findings
- Finding 1 with supporting data
- Finding 2 with supporting data
- Finding 3 with supporting data

## Recommendations
1. Specific actionable recommendation
2. Specific actionable recommendation
```

### For Flexible Guidance

(When adaptation is useful)

```markdown
## Report structure

Here is a sensible default format, but use your best judgment:

# [Analysis Title]

## Executive summary
[Overview]

## Key findings
[Adapt sections based on what you discover]

## Recommendations
[Tailor to the specific context]

Adjust sections as needed for the specific analysis type.
```

---

## Examples Pattern

For skills where output quality depends on seeing examples, provide input/output pairs:

```markdown
## Commit message format

Generate commit messages following these examples:

**Example 1:**
Input: Added user authentication with JWT tokens
Output:
```
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware
```

**Example 2:**
Input: Fixed bug where dates displayed incorrectly in reports
Output:
```
fix(reports): correct date formatting in timezone conversion

Use UTC timestamps consistently across report generation
```

Follow this style: type(scope): brief description, then detailed explanation.
```

Examples help Claude understand the desired style and level of detail more clearly than descriptions alone.

---

## Quality Checklist Pattern

For output that requires validation:

```markdown
## Before Finalizing

Run through this checklist:

- [ ] All required sections present
- [ ] Data validated and sources cited
- [ ] Formatting consistent throughout
- [ ] No placeholder text remaining
- [ ] Links verified and working
- [ ] Spelling and grammar checked
```

---

## Iterative Refinement Pattern

For high-quality outputs:

```markdown
## Output Process

1. Generate initial draft
2. Run quality check script: `scripts/validate_output.py`
3. Address any issues identified
4. Re-validate until all checks pass
5. Present final version to user
```
