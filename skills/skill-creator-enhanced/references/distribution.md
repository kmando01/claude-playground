# Distribution and Sharing

Skills make your MCP integration more complete. As users compare connectors, those with skills offer a faster path to value.

## Current Distribution Model

### How Individual Users Get Skills

1. Download the skill folder
2. Zip the folder (if needed)
3. Upload to Claude.ai via Settings > Capabilities > Skills
4. Or place in Claude Code skills directory

### Organization-Level Skills

- Admins can deploy skills workspace-wide
- Automatic updates
- Centralized management

---

## Distribution Channels

### Claude.ai Plugin Directory

- Available for public skills
- Easy discovery for users

### GitHub Repository

**Recommended approach**:
1. Host on GitHub with a public repo
2. Clear README (for human visitors - separate from skill folder)
3. Example usage with screenshots

### API Distribution

For programmatic use cases:
- `/v1/skills` endpoint for listing and managing skills
- Add skills to Messages API requests via `container.skills` parameter
- Version control through Claude Console
- Works with Claude Agent SDK

**When to use API vs. Claude.ai**:

| Use Case | Best Surface |
|----------|--------------|
| End users interacting directly | Claude.ai / Claude Code |
| Manual testing during development | Claude.ai / Claude Code |
| Individual, ad-hoc workflows | Claude.ai / Claude Code |
| Applications using skills programmatically | API |
| Production deployments at scale | API |
| Automated pipelines and agent systems | API |

---

## Recommended Approach Today

### 1. Host on GitHub

- Public repo for open-source skills
- Clear README with installation instructions
- Example usage and screenshots

### 2. Document in Your MCP Repo

- Link to skills from MCP documentation
- Explain the value of using both together
- Provide quick-start guide

### 3. Create an Installation Guide

```markdown
# Installing the [Your Service] skill

1. Download the skill:
   - Clone repo: `git clone https://github.com/yourcompany/skills`
   - Or download ZIP from Releases

2. Install in Claude:
   - Open Claude.ai > Settings > Skills
   - Click "Upload skill"
   - Select the skill folder (zipped)

3. Enable the skill:
   - Toggle on the [Your Service] skill
   - Ensure your MCP server is connected

4. Test:
   - Ask Claude: "Set up a new project in [Your Service]"
```

---

## Positioning Your Skill

How you describe your skill determines whether users understand its value.

### Focus on Outcomes, Not Features

**Good**:
```
"The ProjectHub skill enables teams to set up complete project 
workspaces in seconds — including pages, databases, and 
templates — instead of spending 30 minutes on manual setup."
```

**Bad**:
```
"The ProjectHub skill is a folder containing YAML frontmatter 
and Markdown instructions that calls our MCP server tools."
```

### Highlight the MCP + Skills Story

```
"Our MCP server gives Claude access to your Linear projects. 
Our skills teach Claude your team's sprint planning workflow. 
Together, they enable AI-powered project management."
```

---

## Resources

- [Skills API Quickstart](https://docs.anthropic.com)
- [Create Custom Skills](https://docs.anthropic.com)
- [Skills in Agent SDK](https://docs.anthropic.com)
- [GitHub: anthropics/skills](https://github.com/anthropics/skills) - Example skills
