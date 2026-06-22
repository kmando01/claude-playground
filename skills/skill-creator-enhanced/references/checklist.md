# Quick Checklist

Use this checklist to validate your skill before and after upload.

---

## Before You Start

- [ ] Identified 2-3 concrete use cases
- [ ] Tools identified (built-in or MCP)
- [ ] Reviewed this guide and example skills
- [ ] Planned folder structure

---

## During Development

### Folder Structure
- [ ] Folder named in kebab-case
- [ ] SKILL.md file exists (exact spelling)
- [ ] No README.md inside skill folder

### YAML Frontmatter
- [ ] Has `---` delimiters
- [ ] `name` field: kebab-case, no spaces, no capitals
- [ ] `description` includes WHAT and WHEN
- [ ] No XML tags (< >) anywhere
- [ ] Under 1024 characters

### Instructions
- [ ] Instructions are clear and actionable
- [ ] Error handling included
- [ ] Examples provided
- [ ] References clearly linked

---

## Before Upload

### Triggering Tests
- [ ] Tested triggering on obvious tasks
- [ ] Tested triggering on paraphrased requests
- [ ] Verified doesn't trigger on unrelated topics

### Functional Tests
- [ ] Functional tests pass
- [ ] Tool integration works (if applicable)
- [ ] Error handling works

### Packaging
- [ ] Compressed as .zip file (if uploading manually)
- [ ] Or run `package_skill.py` for .skill file

---

## After Upload

- [ ] Test in real conversations
- [ ] Monitor for under/over-triggering
- [ ] Collect user feedback
- [ ] Iterate on description and instructions
- [ ] Update version in metadata (if applicable)

---

## Common Issues Quick Reference

| Issue | Solution |
|-------|----------|
| Skill won't upload | Check SKILL.md naming (case-sensitive) |
| Invalid frontmatter | Verify `---` delimiters and YAML syntax |
| Invalid skill name | Use kebab-case only |
| Skill doesn't trigger | Add more keywords to description |
| Skill triggers too often | Be more specific, add negative triggers |
| MCP calls fail | Verify MCP server connected, check tool names |
| Instructions not followed | Put critical instructions at top, be specific |
| Slow responses | Reduce SKILL.md size, move content to references |
