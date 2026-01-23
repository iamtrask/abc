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

---

## 6. Detailed Design: Strategy A with Modal Behavior

This section provides a comprehensive design for the unified positioning system with responsive modal behavior on narrow screens.

### Design Goals

1. **Wide screens**: All margin items (sidenotes + cards) position in the right margin using unified collision avoidance
2. **Narrow screens**: Margin items become modals that open on click and close on click-outside
3. **Unified codebase**: Single system handles both behaviors based on viewport width
4. **Smooth transitions**: Clean switch between modes on resize

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MarginItemManager                        │
├─────────────────────────────────────────────────────────────┤
│  - items: MarginItem[]                                       │
│  - mode: 'margin' | 'modal'                                  │
│  - focusedItem: MarginItem | null                            │
│  - activeModal: MarginItem | null                            │
├─────────────────────────────────────────────────────────────┤
│  + initialize()                                              │
│  + collectItems()                                            │
│  + updateMode()        // Check viewport, switch modes       │
│  + positionAll()       // Margin mode: position in margin    │
│  + openModal(item)     // Modal mode: show as modal          │
│  + closeModal()        // Modal mode: hide modal             │
│  + setFocus(item)      // Margin mode: prioritize item       │
│  + clearFocus()                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       MarginItem                             │
├─────────────────────────────────────────────────────────────┤
│  - element: HTMLElement                                      │
│  - refElement: HTMLElement     // The trigger (sup, span)    │
│  - type: 'sidenote' | 'cite-box'                            │
│  - section: HTMLElement                                      │
│  - targetTop: number                                         │
│  - currentTop: number                                        │
│  - height: number                                            │
└─────────────────────────────────────────────────────────────┘
```

---

### Mode Switching

```javascript
const MARGIN_BREAKPOINT = 1100; // px - matches existing CSS breakpoint

function updateMode() {
    const newMode = window.innerWidth > MARGIN_BREAKPOINT ? 'margin' : 'modal';

    if (newMode !== this.mode) {
        // Clean up old mode
        if (this.mode === 'margin') {
            this.clearFocus();
            this.hideAllInMargin();
        } else if (this.mode === 'modal') {
            this.closeModal();
        }

        // Switch to new mode
        this.mode = newMode;

        // Initialize new mode
        if (this.mode === 'margin') {
            this.showAllInMargin();
            this.positionAll();
        } else {
            this.hideAllInMargin();
            this.setupModalTriggers();
        }
    }
}
```

---

### Margin Mode Behavior

**When**: `window.innerWidth > 1100px`

**Display**: All items visible in right margin, absolutely positioned

**Interactions**:
- **Hover on reference** → Item slides to align with reference, others shift to avoid overlap
- **Hover on item** → Item highlighted, reference highlighted
- **Hover on card avatar** → Author info swaps, items reposition if height changes

**Positioning Algorithm**:
```
function positionAll(focusedItem = null) {
    // 1. Collect all items in each section
    for each section:
        items = collectItemsInSection(section)

        // 2. Calculate target positions (relative to section)
        for each item:
            item.targetTop = item.refElement.offsetTop

        // 3. Sort by target position
        items.sort((a, b) => a.targetTop - b.targetTop)

        // 4. If focused item, position it first at its target
        if (focusedItem && items.includes(focusedItem)):
            focusedItem.currentTop = focusedItem.targetTop
            focusedIndex = items.indexOf(focusedItem)

            // Position items above (push up if needed)
            ceiling = focusedItem.currentTop - GAP
            for i = focusedIndex - 1 down to 0:
                items[i].currentTop = min(items[i].targetTop, ceiling - items[i].height)
                ceiling = items[i].currentTop - GAP

            // Position items below (push down if needed)
            floor = focusedItem.currentTop + focusedItem.height + GAP
            for i = focusedIndex + 1 to items.length:
                items[i].currentTop = max(items[i].targetTop, floor)
                floor = items[i].currentTop + items[i].height + GAP

        // 5. If no focus, simple top-down collision avoidance
        else:
            floor = -Infinity
            for each item:
                item.currentTop = max(item.targetTop, floor)
                floor = item.currentTop + item.height + GAP

        // 6. Apply positions
        for each item:
            item.element.style.top = item.currentTop + 'px'
}
```

---

### Modal Mode Behavior

**When**: `window.innerWidth <= 1100px`

**Display**: Items hidden by default, shown as centered modal on click

**Interactions**:
- **Click on reference** → Modal opens with that item's content
- **Click outside modal** → Modal closes
- **Click on different reference while modal open** → Switch to new item
- **Escape key** → Modal closes

**Modal Structure**:
```html
<div class="margin-item-modal-overlay" aria-hidden="true">
    <div class="margin-item-modal" role="dialog" aria-modal="true">
        <button class="margin-item-modal-close" aria-label="Close">×</button>
        <div class="margin-item-modal-content">
            <!-- Cloned or moved item content -->
        </div>
    </div>
</div>
```

**Modal CSS**:
```css
.margin-item-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s, visibility 0.2s;
}

.margin-item-modal-overlay.is-active {
    opacity: 1;
    visibility: visible;
}

.margin-item-modal {
    background: #fff;
    border: 1px solid #0a0a0a;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    padding: 20px;
    position: relative;
}

.margin-item-modal-close {
    position: absolute;
    top: 8px;
    right: 8px;
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    padding: 4px 8px;
}
```

**Modal JavaScript**:
```javascript
function openModal(item) {
    if (this.activeModal === item) return;

    // Close existing modal if open
    if (this.activeModal) {
        this.closeModal();
    }

    // Create or show overlay
    let overlay = document.querySelector('.margin-item-modal-overlay');
    if (!overlay) {
        overlay = this.createModalOverlay();
        document.body.appendChild(overlay);
    }

    // Clone item content into modal
    const content = overlay.querySelector('.margin-item-modal-content');
    content.innerHTML = '';
    content.appendChild(item.element.cloneNode(true));

    // Show overlay
    overlay.classList.add('is-active');
    overlay.setAttribute('aria-hidden', 'false');

    // Focus management
    overlay.querySelector('.margin-item-modal-close').focus();

    // Track active modal
    this.activeModal = item;

    // Highlight reference
    item.refElement.classList.add('is-highlighted');
}

function closeModal() {
    const overlay = document.querySelector('.margin-item-modal-overlay');
    if (!overlay) return;

    overlay.classList.remove('is-active');
    overlay.setAttribute('aria-hidden', 'true');

    // Remove highlight from reference
    if (this.activeModal) {
        this.activeModal.refElement.classList.remove('is-highlighted');
    }

    this.activeModal = null;
}

function setupModalTriggers() {
    // Click on reference opens modal
    this.items.forEach(item => {
        item.refElement.addEventListener('click', (e) => {
            if (this.mode !== 'modal') return;
            e.preventDefault();
            this.openModal(item);
        });
    });

    // Click outside closes modal
    document.addEventListener('click', (e) => {
        if (this.mode !== 'modal') return;
        if (!this.activeModal) return;

        const overlay = document.querySelector('.margin-item-modal-overlay');
        const modal = overlay?.querySelector('.margin-item-modal');

        if (overlay && !modal.contains(e.target) && !this.isRefElement(e.target)) {
            this.closeModal();
        }
    });

    // Escape key closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.activeModal) {
            this.closeModal();
        }
    });
}
```

---

### Event Handling Summary

| Event | Margin Mode | Modal Mode |
|-------|-------------|------------|
| **Click on reference** | No action (hover-based) | Open modal |
| **Hover on reference** | Focus item, reposition all | No action |
| **Hover on item** | Highlight both | N/A (items hidden) |
| **Click outside** | No action | Close modal |
| **Escape key** | No action | Close modal |
| **Window resize** | Reposition all | Check for mode switch |
| **Avatar hover (card)** | Swap content, reposition | Swap content in modal |

---

### CSS Changes Required

```css
/* Unified margin item base styles */
.margin-item {
    position: absolute;
    left: calc(100% + 20px);
    width: 260px;
    transition: top 0.2s ease-out;
}

/* Apply to both sidenotes and cite-boxes */
.sidenote,
.cite-box {
    /* Inherit from .margin-item or duplicate styles */
}

/* Modal mode: hide items in margin */
@media (max-width: 1100px) {
    .sidenote,
    .cite-box {
        display: none !important;
    }
}

/* Remove wrapper positioning (cards position relative to section) */
.cite-box-wrapper {
    position: static;
}
```

---

### Migration Path: Step-by-Step Implementation

Each phase ends with a **visual checkpoint** you can verify in the browser before proceeding.

---

#### Phase 1: Sidenotes Position via Unified System

**Goal**: Replace sidenote positioning with new unified function. Cards unchanged.

**Changes**:
1. Add new `collectMarginItems()` and `positionMarginItems()` functions
2. Replace `alignSidenotes()` calls with new unified function
3. Keep all card code unchanged for now

**Code**:
```javascript
function collectMarginItems(section) {
    const sidenotes = Array.from(section.querySelectorAll('.sidenote'));
    // Note: NOT including cite-boxes yet

    return sidenotes.map(element => ({
        element,
        type: 'sidenote',
        refElement: document.querySelector(`a[href="#${element.id}"]`),
        section,
        targetTop: 0,
        height: element.offsetHeight
    }));
}

function positionMarginItems(items, focusedItem = null) {
    const GAP = 16;

    // Calculate target positions
    items.forEach(item => {
        if (item.refElement) {
            const refRect = item.refElement.getBoundingClientRect();
            const sectionRect = item.section.getBoundingClientRect();
            item.targetTop = refRect.top - sectionRect.top;
        }
    });

    // Sort by target position
    items.sort((a, b) => a.targetTop - b.targetTop);

    // Simple collision avoidance (no focus yet)
    let lastBottom = -Infinity;
    items.forEach(item => {
        const adjustedTop = Math.max(item.targetTop, lastBottom + GAP);
        item.element.style.top = `${adjustedTop}px`;
        lastBottom = adjustedTop + item.height;
    });
}

// Replace old alignSidenotes calls:
function alignSidenotes() {
    if (window.matchMedia('(max-width: 1024px)').matches) return;

    document.querySelectorAll('section').forEach(section => {
        const items = collectMarginItems(section);
        positionMarginItems(items);
    });
}
```

**✅ Visual Checkpoint 1**:
| Test | Expected Result |
|------|-----------------|
| Load page on wide screen | Sidenotes appear in right margin |
| Sidenotes near their references | Each sidenote aligns with its superscript number |
| Multiple sidenotes don't overlap | Sidenotes stack with gaps between them |
| Cards still work | Cards position and hover as before (unchanged) |
| Resize window | Sidenotes reposition correctly |

---

#### Phase 2: Cards Join Unified System (No Hover Yet)

**Goal**: Cards position via unified system alongside sidenotes. Hover disabled temporarily.

**Changes**:
1. Remove `position: relative` from `.cite-box-wrapper`
2. Add cite-boxes to `collectMarginItems()`
3. Disable card hover repositioning temporarily
4. All items (sidenotes + cards) avoid overlapping

**CSS Change**:
```css
.cite-box-wrapper {
    /* Remove: position: relative; */
}
```

**Code Change**:
```javascript
function collectMarginItems(section) {
    const sidenotes = Array.from(section.querySelectorAll('.sidenote'));
    const citeBoxes = Array.from(section.querySelectorAll('.cite-box'));

    const items = [];

    sidenotes.forEach(element => {
        items.push({
            element,
            type: 'sidenote',
            refElement: document.querySelector(`a[href="#${element.id}"]`),
            section,
            targetTop: 0,
            height: element.offsetHeight
        });
    });

    citeBoxes.forEach(element => {
        const refId = element.getAttribute('data-ref');
        items.push({
            element,
            type: 'cite-box',
            refElement: document.getElementById(refId),
            section,
            targetTop: 0,
            height: element.offsetHeight
        });
    });

    return items;
}

// Temporarily disable card hover repositioning
// (Comment out setActiveCite calls)
```

**✅ Visual Checkpoint 2**:
| Test | Expected Result |
|------|-----------------|
| Load page on wide screen | Both sidenotes AND cards appear in margin |
| Sidenotes and cards don't overlap | All items stack with gaps, no overlapping |
| Cards near their citation references | Each card aligns with its (A) superscript |
| Scroll down page | Items stay aligned with their references |
| Card hover highlighting works | Hovering card highlights its reference (but no repositioning) |

---

#### Phase 3: Card Hover Focus Restored

**Goal**: Restore card hover behavior - hovered card gets priority positioning.

**Changes**:
1. Add `focusedItem` parameter support to `positionMarginItems()`
2. Re-enable hover event handlers
3. Focused card moves to its target, others shift around it

**Code Change**:
```javascript
function positionMarginItems(items, focusedItem = null) {
    const GAP = 16;

    // Calculate target positions
    items.forEach(item => {
        if (item.refElement) {
            const refRect = item.refElement.getBoundingClientRect();
            const sectionRect = item.section.getBoundingClientRect();
            item.targetTop = refRect.top - sectionRect.top;
        }
    });

    // Sort by target position
    items.sort((a, b) => a.targetTop - b.targetTop);

    // Find focused item index
    const focusedIndex = focusedItem ? items.indexOf(focusedItem) : -1;

    if (focusedIndex >= 0) {
        // Position focused item at its target
        const focused = items[focusedIndex];
        focused.element.style.top = `${focused.targetTop}px`;

        // Position items above (push up if needed)
        let ceiling = focused.targetTop - GAP;
        for (let i = focusedIndex - 1; i >= 0; i--) {
            const top = Math.min(items[i].targetTop, ceiling - items[i].height);
            items[i].element.style.top = `${Math.max(0, top)}px`;
            ceiling = Math.max(0, top) - GAP;
        }

        // Position items below (push down if needed)
        let floor = focused.targetTop + focused.height + GAP;
        for (let i = focusedIndex + 1; i < items.length; i++) {
            const top = Math.max(items[i].targetTop, floor);
            items[i].element.style.top = `${top}px`;
            floor = top + items[i].height + GAP;
        }
    } else {
        // No focus: simple top-down collision avoidance
        let lastBottom = -Infinity;
        items.forEach(item => {
            const adjustedTop = Math.max(item.targetTop, lastBottom + GAP);
            item.element.style.top = `${adjustedTop}px`;
            lastBottom = adjustedTop + item.height;
        });
    }
}
```

**✅ Visual Checkpoint 3**:
| Test | Expected Result |
|------|-----------------|
| Hover on citation (A) in text | Associated card slides to align with citation |
| Other items shift | Sidenotes and other cards move to avoid overlap |
| Hover on different citation | New card gets focus, items re-arrange |
| Stop hovering | Items return to default positions (after timeout) |
| Avatar hover on card | Author swaps, card resizes, other items adjust |

---

#### Phase 4: Modal Mode for Narrow Screens

**Goal**: On narrow screens, hide margin items and show them as modals on click.

**Changes**:
1. Add CSS to hide margin items below breakpoint
2. Add modal overlay HTML/CSS
3. Add click handlers for references
4. Implement open/close modal functions

**CSS**:
```css
/* Hide margin items on narrow screens */
@media (max-width: 1100px) {
    .sidenote,
    .cite-box {
        /* Don't use display:none - we need them for modal content */
        position: fixed !important;
        left: -9999px !important;
        visibility: hidden;
    }
}

/* Modal styles */
.margin-item-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s, visibility 0.2s;
}

.margin-item-modal-overlay.is-active {
    opacity: 1;
    visibility: visible;
}

.margin-item-modal {
    background: #fff;
    border: 1px solid #0a0a0a;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    padding: 20px;
    position: relative;
}

.margin-item-modal-close {
    position: absolute;
    top: 8px;
    right: 12px;
    background: none;
    border: none;
    font-size: 28px;
    cursor: pointer;
    line-height: 1;
}
```

**JavaScript**:
```javascript
const MODAL_BREAKPOINT = 1100;

function isModalMode() {
    return window.innerWidth <= MODAL_BREAKPOINT;
}

function openMarginModal(item) {
    let overlay = document.querySelector('.margin-item-modal-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'margin-item-modal-overlay';
        overlay.innerHTML = `
            <div class="margin-item-modal" role="dialog" aria-modal="true">
                <button class="margin-item-modal-close" aria-label="Close">&times;</button>
                <div class="margin-item-modal-content"></div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeMarginModal();
        });

        // Close button
        overlay.querySelector('.margin-item-modal-close').addEventListener('click', closeMarginModal);
    }

    // Clone content into modal
    const content = overlay.querySelector('.margin-item-modal-content');
    content.innerHTML = '';
    const clone = item.element.cloneNode(true);
    clone.style.cssText = 'position:static;visibility:visible;left:auto;';
    content.appendChild(clone);

    overlay.classList.add('is-active');
    item.refElement?.classList.add('is-highlighted');

    // Store active item for cleanup
    overlay.dataset.activeItemId = item.element.id;
}

function closeMarginModal() {
    const overlay = document.querySelector('.margin-item-modal-overlay');
    if (!overlay) return;

    overlay.classList.remove('is-active');

    // Remove highlight
    const itemId = overlay.dataset.activeItemId;
    if (itemId) {
        const item = document.getElementById(itemId);
        const refSelector = item?.classList.contains('sidenote')
            ? `a[href="#${itemId}"]`
            : `#${item?.getAttribute('data-ref')}`;
        document.querySelector(refSelector)?.classList.remove('is-highlighted');
    }
}

// Add click handlers for modal mode
document.addEventListener('click', (e) => {
    if (!isModalMode()) return;

    // Check if clicked a sidenote ref
    const sidenoteRef = e.target.closest('.sidenote-ref');
    if (sidenoteRef) {
        e.preventDefault();
        const targetId = sidenoteRef.getAttribute('href');
        const sidenote = document.querySelector(targetId);
        if (sidenote) {
            openMarginModal({
                element: sidenote,
                refElement: sidenoteRef
            });
        }
        return;
    }

    // Check if clicked a cite-box ref
    const citeRef = e.target.closest('.cite-box-ref');
    if (citeRef) {
        e.preventDefault();
        const boxId = citeRef.getAttribute('data-box');
        const box = document.getElementById(boxId);
        if (box) {
            openMarginModal({
                element: box,
                refElement: citeRef
            });
        }
        return;
    }
});

// Escape to close
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMarginModal();
});
```

**✅ Visual Checkpoint 4**:
| Test | Expected Result |
|------|-----------------|
| Narrow window (< 1100px) | Sidenotes and cards NOT visible in margin |
| Click footnote superscript | Modal opens with sidenote content |
| Click citation (A) | Modal opens with card content |
| Click outside modal | Modal closes |
| Press Escape | Modal closes |
| Click different reference while modal open | Modal switches to new content |
| Widen window (> 1100px) | Margin items reappear, click does nothing |

---

#### Phase 5: Polish and Cleanup

**Goal**: Remove old code, ensure smooth transitions, final polish.

**Changes**:
1. Delete old `alignSidenotes()`, `positionCiteBoxes()`, `getCiteBoxData()`
2. Delete old hover event handlers (consolidated into new system)
3. Add smooth transitions for margin mode
4. Ensure avatar hover works in modal mode too

**CSS Polish**:
```css
/* Smooth transitions for margin items */
.sidenote,
.cite-box {
    transition: top 0.2s ease-out;
}

/* Prevent transition on page load */
.no-transition .sidenote,
.no-transition .cite-box {
    transition: none;
}
```

**✅ Visual Checkpoint 5 (Final)**:
| Test | Expected Result |
|------|-----------------|
| All Phase 1-4 tests pass | No regressions |
| Smooth animations | Items slide smoothly when repositioning |
| No console errors | Clean console on all interactions |
| Avatar hover in modal | Clicking avatar in modal swaps author info |
| Resize across breakpoint | Clean switch between margin and modal modes |
| Page load | No flickering or jumping on initial load |

---

### Summary: Visual Checkpoints

| Phase | What You'll See |
|-------|-----------------|
| **1** | Sidenotes position correctly (cards unchanged) |
| **2** | Sidenotes + cards both in margin, no overlaps |
| **3** | Hovering citation makes card slide into position |
| **4** | Narrow screen: click opens modal, click-out closes |
| **5** | Smooth animations, no console errors, polished |

### Files to Modify

| File | Changes |
|------|---------|
| `styles.css` | Remove wrapper positioning, add modal styles, add transitions |
| `main.js` | Replace positioning functions, add modal logic |
| `index.html` | No changes needed (modal created via JS) |

### Rollback Points

Each phase has a git commit. To rollback:

```bash
# See commits
git log --oneline

# Rollback to specific phase
git checkout <commit-hash> -- main.js styles.css
```

| After Phase | Rollback Command | Result |
|-------------|------------------|--------|
| 1 | `git checkout HEAD~1 -- main.js` | Original sidenote code restored |
| 2 | `git checkout HEAD~1 -- main.js styles.css` | Cards use old positioning |
| 3 | `git checkout HEAD~1 -- main.js` | No hover focus |
| 4 | `git checkout HEAD~1 -- main.js styles.css` | No modal mode |
| 5 | `git checkout HEAD~1 -- main.js styles.css` | Before cleanup |
