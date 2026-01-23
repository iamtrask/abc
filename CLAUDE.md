# CLAUDE.md

## Project Overview
This is an academic thesis website about Attribution-Based Control in AI Systems. The site consists of multiple HTML chapter pages styled with a shared `styles.css`.

## Key Files
- `index.html` - Main introduction/landing page
- `chapter2.html` through `chapter5.html` - Chapter content
- `appendix1.html`, `appendix2.html` - Appendices
- `styles.css` - All styling (single shared stylesheet)

## Existing UI Patterns to Reference
When building new tooltip/sidebar/thumbnail features, study these existing patterns in `styles.css`:

- **Sidenotes** (lines ~803-867): `.sidenote-ref` and `.sidenote` classes
  - Absolutely positioned margin content
  - Hover highlighting with `.is-highlighted`
  - Responsive collapse at 1399px breakpoint

- **TOC Sidebar** (lines ~82-145): `.toc-sidebar`
  - Sticky positioning
  - Scroll behavior

- **ASCII Margin Art** (lines ~88-112 in HTML): `.ascii-margin`, `.art-piece`
  - Floating decorative elements

## Workflow Rules

### CRITICAL: Commit After Every Change
After ANY modification to HTML or CSS files, immediately run:
```bash
git add -A && git commit -m "descriptive message"
```
This enables easy rollback if a change doesn't work out. Never batch multiple changes into one commit.

### Make Small, Incremental Changes
1. Make ONE small change at a time
2. Commit it
3. Wait for user feedback before proceeding
4. If user approves, continue; if not, `git revert HEAD` or `git checkout HEAD~1 -- <file>`

## Common Pitfalls to Avoid

### CSS Issues
- **Check responsive breakpoints**: This site has breakpoints at 1399px, 1100px, 900px, 768px, 600px. New features must work at all sizes.
- **Don't break existing sidenotes**: The sidenote system uses absolute positioning - be careful adding position rules that could interfere.
- **Preserve the color scheme**: Primary text is `#0a0a0a`, links are `#0066cc`, background is `#fff`.
- **Match existing font sizes**: Body is 18px, sidenotes are 12px.

### HTML Issues
- **Keep structure consistent**: All pages share the same nav, `.wrapper`, `.page-container` structure.
- **Don't add inline styles**: All styles go in `styles.css`.
- **Preserve accessibility**: Keep semantic HTML, maintain link text clarity.

### Process Issues
- **Don't make multiple changes before committing**: One change = one commit.
- **Don't refactor unrelated code**: Only touch what's needed for the current feature.
- **Don't add JavaScript unless explicitly requested**: Prefer CSS-only solutions.
- **Read existing code before modifying**: Always `Read` the relevant section before editing.

## Testing Checklist
Before considering any change complete:
1. Does it work on wide screens (>1400px)?
2. Does it work on medium screens (900-1399px)?
3. Does it work on mobile (<768px)?
4. Does it break existing sidenotes?
5. Does it break the TOC sidebar?
6. Is the styling consistent with the rest of the site?

## When Uncertain
If requirements are unclear, ASK before implementing. It's better to clarify than to build the wrong thing and need multiple reverts.
