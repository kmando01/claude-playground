# Defining Success Criteria

How will you know your skill is working? These are aspirational targets - rough benchmarks rather than precise thresholds.

## Quantitative Metrics

### Skill triggers on 90% of relevant queries

**How to measure**: 
- Run 10-20 test queries that should trigger your skill
- Track how many times it loads automatically vs. requires explicit invocation

**Example test queries for a "project-setup" skill**:
- "Help me set up a new ProjectHub workspace" ✓
- "I need to create a project in ProjectHub" ✓
- "Initialize a ProjectHub project for Q4 planning" ✓
- "What's the weather in San Francisco?" ✗ (should NOT trigger)

---

### Completes workflow in X tool calls

**How to measure**: 
- Compare the same task with and without the skill enabled
- Count tool calls and total tokens consumed

**Example comparison**:
```
Without skill:
- 15 back-and-forth messages
- 3 failed API calls requiring retry
- 12,000 tokens consumed

With skill:
- 2 clarifying questions only
- 0 failed API calls
- 6,000 tokens consumed
```

---

### 0 failed API calls per workflow

**How to measure**: 
- Monitor MCP server logs during test runs
- Track retry rates and error codes

---

## Qualitative Metrics

### Users don't need to prompt Claude about next steps

**How to assess**: 
- During testing, note how often you need to redirect or clarify
- Ask beta users for feedback

---

### Workflows complete without user correction

**How to assess**: 
- Run the same request 3-5 times
- Compare outputs for structural consistency and quality

---

### Consistent results across sessions

**How to assess**: 
- Can a new user accomplish the task on first try with minimal guidance?

---

## Testing Approach

### 1. Triggering Tests

**Goal**: Ensure your skill loads at the right times.

```markdown
Should trigger:
- "Help me set up a new ProjectHub workspace"
- "I need to create a project in ProjectHub"
- "Initialize a ProjectHub project for Q4 planning"

Should NOT trigger:
- "What's the weather in San Francisco?"
- "Help me write Python code"
- "Create a spreadsheet" (unless your skill handles sheets)
```

### 2. Functional Tests

**Goal**: Verify the skill produces correct outputs.

```markdown
Test: Create project with 5 tasks

Given: Project name "Q4 Planning", 5 task descriptions

When: Skill executes workflow

Then:
  - Project created in ProjectHub
  - 5 tasks created with correct properties
  - All tasks linked to project
  - No API errors
```

### 3. Performance Comparison

**Goal**: Prove the skill improves results vs. baseline.

Compare metrics before and after skill implementation.

---

## Pro Tip: Single Task Iteration

The most effective skill creators iterate on a single challenging task until Claude succeeds, then extract the winning approach into a skill.

This leverages Claude's in-context learning and provides faster signal than broad testing. Once you have a working foundation, expand to multiple test cases for coverage.
