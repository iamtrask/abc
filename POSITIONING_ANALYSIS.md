# Margin Item Positioning Analysis

## Current Systems Overview

This document analyzes how footnotes (sidenotes) and resource cards (cite-boxes) are positioned in the margin, and proposes strategies for integrating them.

---

## 1. How Sidenotes (Footnotes) Are Positioned

### Positioning Context
- **CSS**: Sidenotes have `position: absolute` and are direct children of `<section>` elements
- **Reference point**: Each section has `position: relative` (implicit), making it the positioning context
- **Target position**: Calculated as `ref.getBoundingClientRect().top - section.getBoundingClientRect().top`

### When Positioning Runs
- `DOMContentLoaded`
- `window.load`
- `document.fonts.ready`
- `window.resize`

**Note**: Sidenote positions are **static** - they don't change based on user interaction.

### Algorithm (Two Phases)

**Phase 1 - Initial Placement:**
```
For each sidenote-ref in the document:
  1. Find the sidenote it references
  2. Calculate the ref's vertical position relative to its section
  3. Set sidenote.style.top to that position
```

**Phase 2 - Collision Avoidance:**
```
For each section:
  1. Collect all sidenotes in that section
  2. Sort by their top position
  3. For each sidenote (top to bottom):
     - If it overlaps with the previous sidenote, push it down
     - Track the bottom of this sidenote for the next iteration
```

### Key Characteristics
- Sidenotes always try to align with their reference first
- Collisions are resolved by pushing items **downward only**
- No concept of "focus" or priority
- Gap between sidenotes: **12px**

---

## 2. How Cite-Boxes (Cards) Are Positioned

### Positioning Context
- **CSS**: Cite-boxes have `position: absolute` inside `.cite-box-wrapper`
- **Reference point**: The wrapper has `position: relative`, making it the positioning context
- **Target position**: Calculated as `ref.getBoundingClientRect().top - wrapper.getBoundingClientRect().top`

### When Positioning Runs
- `DOMContentLoaded`
- `window.load`
- `window.resize`
- **On hover** (citation reference or card)
- **On avatar hover** (when author info changes and card height changes)

**Note**: Card positions are **dynamic** - they change based on user interaction.

### Algorithm (Focus-Aware)

**Default Mode (no focus):**
```
1. Collect all cite-boxes with data-ref attribute
2. Calculate each box's target position (relative to wrapper)
3. Sort by target position
4. For each box (top to bottom):
   - Position at target, or push down if overlapping previous box
   - Track bottom for next iteration
```

**Focused Mode (on hover):**
```
1. Collect all cite-boxes, calculate targets, sort
2. Find the focused box's index in sorted order
3. Position focused box at its exact target position
4. For boxes ABOVE focused (bottom to top):
   - Position at target, or push UP if would overlap focused box
5. For boxes BELOW focused (top to bottom):
   - Position at target, or push DOWN if overlapping previous
```

### Key Characteristics
- Focused box gets priority positioning at its ideal location
- Other boxes shift to accommodate the focused one
- Boxes can move **both up and down**
- Gap between boxes: **20px**
- 10-second timeout before positions reset after hover ends

---

## 3. Key Differences Between the Systems

| Aspect | Sidenotes | Cite-Boxes |
|--------|-----------|------------|
| **Positioning context** | Section | Wrapper (inside section) |
| **Trigger** | Page load, resize, fonts | Load, resize, AND hover events |
| **Interactivity** | Static | Dynamic (responds to hover) |
| **Focus concept** | No | Yes (hovered item gets priority) |
| **Collision resolution** | Push down only | Push up or down around focus |
| **Gap size** | 12px | 20px |
| **Awareness of other system** | None | None |

### The Core Problem
Both systems operate independently and are **completely unaware of each other**. When cards are positioned relative to their wrapper, and sidenotes are positioned relative to the section, they can overlap because:

1. They use different coordinate systems
2. Neither system knows where the other has placed items
3. Cards may be positioned in the same vertical space as sidenotes

---

## 4. Proposed Integration Strategies

### Strategy A: Unified Positioning Context

**Approach**: Make cards position relative to the section (like sidenotes) and create a single function that handles both.

**Changes Required**:
- Remove `position: relative` from `.cite-box-wrapper`
- Modify `getCiteBoxData()` to calculate positions relative to section
- Create unified `alignAllMarginItems()` function that:
  1. Collects both sidenotes AND cite-boxes
  2. Calculates target positions for all (relative to section)
  3. Sorts all items by target position
  4. Applies collision avoidance across the combined set

**On Hover**:
- Focused card gets its target position
- All other items (sidenotes AND cards) shift to avoid overlap

**Pros**:
- Simple mental model - one system handles everything
- Guaranteed no overlaps between any items
- Consistent gap spacing

**Cons**:
- Sidenotes might move on card hover (design change)
- More items to reposition on every hover event
- Wrapper element loses its positioning purpose

---

### Strategy B: Two-Phase System with Region Awareness

**Approach**: Keep separate systems but make them aware of each other's "occupied regions."

**Changes Required**:
- After `alignSidenotes()` runs, calculate occupied vertical regions
- Pass these regions to `positionCiteBoxes()` as "blocked zones"
- Card system avoids sidenote regions in addition to other cards

**Algorithm**:
```
1. alignSidenotes() runs first, positions all sidenotes
2. Calculate occupied regions: [{top: N, bottom: M}, ...]
3. positionCiteBoxes(focusedRefId, occupiedRegions):
   - Position cards avoiding both other cards AND occupied regions
```

**Pros**:
- Sidenotes remain completely static (original design preserved)
- Clear separation of concerns
- Minimal changes to existing code

**Cons**:
- Two coordinate systems still in play (wrapper vs section)
- Need to translate between coordinate systems
- More complex logic to handle blocked regions
- Cards might get pushed far from their targets if sidenotes occupy ideal positions

---

### Strategy C: Priority-Based Unified System

**Approach**: Single positioning system with priority levels that determine which items can displace others.

**Priority Levels**:
1. **Highest**: Sidenotes (never move after initial positioning)
2. **High**: Focused/hovered card (gets its target position if possible)
3. **Normal**: Other cards (fill remaining space)

**Algorithm**:
```
1. Collect all margin items (sidenotes + cards)
2. Assign priorities
3. Sort by target position
4. Position highest-priority items first (at their targets)
5. Position lower-priority items in remaining gaps
6. Lower-priority items cannot displace higher-priority items
```

**On Hover**:
- Hovered card's priority elevates to "High"
- Repositioning respects sidenotes (they don't move)
- Other cards shift around both sidenotes and focused card

**Pros**:
- Preserves sidenote stability (design requirement)
- Cards get dynamic behavior (design requirement)
- Clear, predictable rules for conflict resolution
- Unified coordinate system

**Cons**:
- Most complex to implement
- Need to handle edge cases (what if focused card's target is blocked by sidenote?)
- May require fallback positions when ideal positions are unavailable

---

## 5. Recommendation

### Recommended Strategy: **Strategy C (Priority-Based Unified System)**

**Rationale**:

1. **Preserves Original Design Intent**
   - Sidenotes were designed to be stable, scholarly footnotes that don't jump around
   - Cards were designed to be interactive, responding to user focus
   - Strategy C preserves both behaviors

2. **Unified Coordinate System**
   - Using section as the positioning context for both eliminates translation errors
   - Simplifies the math and reduces bugs

3. **Predictable Behavior**
   - Clear priority rules mean users can predict what will happen
   - Sidenotes: "These never move"
   - Cards: "The one I'm looking at comes to me, others make room"

4. **Graceful Degradation**
   - If a card can't get its ideal position (blocked by sidenote), it gets the nearest available position
   - No overlaps, even in edge cases

5. **Future-Proof**
   - Easy to add new margin item types with their own priority levels
   - Could support pinned items, ads, or other content

### Implementation Notes for Strategy C

1. **CSS Change**: Remove `position: relative` from `.cite-box-wrapper`

2. **Data Structure**:
   ```javascript
   {
     element: HTMLElement,
     type: 'sidenote' | 'cite-box',
     targetTop: number,
     height: number,
     priority: 'fixed' | 'focused' | 'normal'
   }
   ```

3. **Key Functions**:
   - `collectAllMarginItems(section)` - gather sidenotes and cards
   - `calculateTargetPositions(items)` - compute ideal positions
   - `assignPriorities(items, focusedElement)` - set priority levels
   - `positionWithPriority(items)` - place items respecting priorities

4. **Edge Case Handling**:
   - If focused card's target overlaps a sidenote, position it just below the sidenote
   - If no room exists, cards stack at the bottom of available space
   - Minimum gap should be consistent (suggest 16px as compromise between 12px and 20px)
