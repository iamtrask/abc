// Scroll spy for TOC
document.addEventListener('DOMContentLoaded', function () {
    const tocLinks = document.querySelectorAll('.toc-sidebar a');
    const sections = [];

    tocLinks.forEach((link) => {
        const id = link.getAttribute('href')?.substring(1);
        const section = document.getElementById(id);
        if (section) {
            sections.push({ id, element: section, link });
        }
    });

    function updateActiveLink() {
        const header = document.querySelector('nav');
        const OFFSET = header ? header.offsetHeight + 20 : 120;
        let currentSection = sections[0];

        for (const section of sections) {
            const rect = section.element.getBoundingClientRect();
            if (rect.top - OFFSET <= 0) {
                currentSection = section;
            }
        }

        tocLinks.forEach((link) => link.classList.remove('active'));
        if (currentSection) {
            currentSection.link.classList.add('active');
        }
    }

    window.addEventListener('scroll', updateActiveLink, { passive: true });
    window.addEventListener('resize', updateActiveLink);
    updateActiveLink();
});

/**
 * Update header.
 */
let lastScrollTop = 0;

function updateHeader() {
    const header = document.querySelector('nav');
    const scrollTop = window.scrollY;
    const shouldHide = scrollTop > lastScrollTop && scrollTop > 100;

    header.classList.toggle('is-hide', shouldHide);
    const headerHeight = header.offsetHeight;
    document.documentElement.style.setProperty('--header-height', `${headerHeight}px`);
    lastScrollTop = scrollTop;
}

/**
 * Events.
 */
document.addEventListener('scroll', updateHeader);
window.addEventListener('resize', updateHeader);

/**
 * Unified margin item positioning system.
 */
const MARGIN_GAP = 20;

function collectMarginItems(section) {
    // Phase 2: Collect both sidenotes and cite-boxes
    const sidenotes = Array.from(section.querySelectorAll('.sidenote'));
    const citeBoxes = Array.from(section.querySelectorAll('.cite-box[data-ref]'));

    const sidenoteItems = sidenotes.map(element => ({
        element,
        type: 'sidenote',
        refElement: document.querySelector(`a[href="#${element.id}"]`),
        section,
        targetTop: 0,
        height: element.offsetHeight
    }));

    const citeBoxItems = citeBoxes.map(element => {
        const refId = element.getAttribute('data-ref');
        return {
            element,
            type: 'cite-box',
            refElement: document.getElementById(refId),
            section,
            targetTop: 0,
            height: element.offsetHeight
        };
    });

    return [...sidenoteItems, ...citeBoxItems];
}

function positionMarginItems(items, focusedItem = null) {
    if (items.length === 0) return;

    // Calculate target positions (relative to section)
    items.forEach(item => {
        if (item.refElement) {
            const refRect = item.refElement.getBoundingClientRect();
            const sectionRect = item.section.getBoundingClientRect();
            item.targetTop = refRect.top - sectionRect.top;
        }
        // Refresh height in case content changed
        item.height = item.element.offsetHeight;
    });

    // Sort by target position
    items.sort((a, b) => a.targetTop - b.targetTop);

    // Phase 3: Focus-aware positioning
    const focusedIndex = focusedItem ? items.indexOf(focusedItem) : -1;

    if (focusedIndex >= 0) {
        const focused = items[focusedIndex];

        // First, calculate how much space items above need
        let spaceNeededAbove = 0;
        for (let i = 0; i < focusedIndex; i++) {
            spaceNeededAbove += items[i].height + MARGIN_GAP;
        }

        // Position focused item - push down if items above need more space
        const focusedTop = Math.max(focused.targetTop, spaceNeededAbove);
        focused.element.style.top = `${focusedTop}px`;

        // Position items above (push up from focused item)
        let ceiling = focusedTop - MARGIN_GAP;
        for (let i = focusedIndex - 1; i >= 0; i--) {
            const top = Math.min(items[i].targetTop, ceiling - items[i].height);
            const clampedTop = Math.max(0, top);
            items[i].element.style.top = `${clampedTop}px`;
            ceiling = clampedTop - MARGIN_GAP;
        }

        // Position items below (push down if needed)
        let floor = focusedTop + focused.height + MARGIN_GAP;
        for (let i = focusedIndex + 1; i < items.length; i++) {
            const top = Math.max(items[i].targetTop, floor);
            items[i].element.style.top = `${top}px`;
            floor = top + items[i].height + MARGIN_GAP;
        }
    } else {
        // No focus: simple top-down collision avoidance
        let lastBottom = -Infinity;
        items.forEach(item => {
            const adjustedTop = Math.max(item.targetTop, lastBottom + MARGIN_GAP);
            item.element.style.top = `${adjustedTop}px`;
            lastBottom = adjustedTop + item.height;
        });
    }
}

// Phase 3: Track focused margin item for hover behavior
let focusedMarginElement = null;
let focusResetTimeout = null;

/**
 * Align margin items using unified positioning system.
 * @param {HTMLElement|null} focusedElement - Element to focus (gets priority positioning)
 */
function alignMarginItems(focusedElement = null) {
    if (window.matchMedia('(max-width: 1024px)').matches) return;

    document.querySelectorAll('section').forEach(section => {
        const items = collectMarginItems(section);
        // Find the focused item in this section's items
        const focusedItem = focusedElement
            ? items.find(item => item.element === focusedElement)
            : null;
        positionMarginItems(items, focusedItem);
    });
}

/**
 * Align side notes using unified positioning system (legacy name for compatibility).
 */
function alignSidenotes() {
    alignMarginItems(focusedMarginElement);
}

function resizeSidenotes() {
    const main = document.querySelector('main');
    if (!main) return;

    const mainRect = main.getBoundingClientRect();
    const viewportWidth = window.innerWidth;

    const GAP = 20;
    const availableRightSpace = viewportWidth - mainRect.right - GAP;

    const MIN = 160;
    const MAX = 340;

    const sidenoteWidth = Math.max(MIN, Math.min(MAX, availableRightSpace));

    document.querySelectorAll('.sidenote').forEach((sn) => {
        sn.style.width = `${sidenoteWidth}px`;
    });

    // Apply same width to cite-boxes
    document.querySelectorAll('.cite-box').forEach((box) => {
        box.style.width = `${sidenoteWidth}px`;
    });
}

function setupSidenoteHover() {
    document.querySelectorAll('.sidenote-ref').forEach((ref) => {
        const targetId = ref.getAttribute('href');
        if (!targetId || !targetId.startsWith('#')) return;

        const sidenote = document.querySelector(targetId);
        if (!sidenote) return;

        ref.addEventListener('mouseenter', () => {
            sidenote.classList.add('is-highlighted');
            ref.classList.add('is-highlighted');
        });

        ref.addEventListener('mouseleave', () => {
            sidenote.classList.remove('is-highlighted');
            ref.classList.remove('is-highlighted');
        });

        sidenote.addEventListener('mouseenter', () => {
            sidenote.classList.add('is-highlighted');
            ref.classList.add('is-highlighted');
        });

        sidenote.addEventListener('mouseleave', () => {
            sidenote.classList.remove('is-highlighted');
            ref.classList.remove('is-highlighted');
        });
    });
}

function initializeSidenotes() {
    resizeSidenotes();
    alignSidenotes();
    setupSidenoteHover();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSidenotes);
} else {
    initializeSidenotes();
}

window.addEventListener('load', initializeSidenotes);

if (document.fonts) {
    document.fonts.ready.then(initializeSidenotes);
}

window.addEventListener('resize', initializeSidenotes);

// Cite-box hover highlighting (Phase 3: positioning via unified system)
function initializeCiteBoxes() {
    // Phase 3: Positioning with focus support

    // Hover on box -> highlight citation, maintain focus
    document.querySelectorAll('.cite-box[data-ref]').forEach((box) => {
        const refId = box.getAttribute('data-ref');
        const ref = document.getElementById(refId);
        if (!ref) return;

        box.addEventListener('mouseenter', () => {
            if (focusResetTimeout) {
                clearTimeout(focusResetTimeout);
                focusResetTimeout = null;
            }
            // Clear other highlights first
            document.querySelectorAll('.cite-box.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            document.querySelectorAll('.cite-box-ref.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            ref.classList.add('is-highlighted');
            box.classList.add('is-highlighted');
            // Keep this box focused
            focusedMarginElement = box;
        });

        box.addEventListener('mouseleave', () => {
            // Delay clearing so user can move between citation and box
            focusResetTimeout = setTimeout(() => {
                ref.classList.remove('is-highlighted');
                box.classList.remove('is-highlighted');
                focusedMarginElement = null;
                alignMarginItems();
            }, 150);
        });
    });

    // Hover on citation -> highlight box and reposition with focus
    document.querySelectorAll('.cite-box-ref[data-box]').forEach((ref) => {
        const boxId = ref.getAttribute('data-box');
        const box = document.getElementById(boxId);
        if (!box) return;

        ref.addEventListener('mouseenter', () => {
            if (focusResetTimeout) {
                clearTimeout(focusResetTimeout);
                focusResetTimeout = null;
            }
            // Clear other highlights first
            document.querySelectorAll('.cite-box.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            document.querySelectorAll('.cite-box-ref.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            box.classList.add('is-highlighted');
            ref.classList.add('is-highlighted');
            // Focus this box and reposition
            focusedMarginElement = box;
            alignMarginItems(box);
        });

        ref.addEventListener('mouseleave', () => {
            // Delay clearing so user can move between citation and box
            focusResetTimeout = setTimeout(() => {
                box.classList.remove('is-highlighted');
                ref.classList.remove('is-highlighted');
                focusedMarginElement = null;
                alignMarginItems();
            }, 150);
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeCiteBoxes);
// Phase 2: Removed load/resize handlers - unified system handles positioning

// Avatar hover to swap author info
function initializeAvatarHover() {
    document.querySelectorAll('.cite-box-avatars img').forEach((avatar) => {
        avatar.addEventListener('mouseenter', () => {
            const citeBox = avatar.closest('.cite-box');
            if (!citeBox) return;

            const name = avatar.getAttribute('data-name');
            const affiliation = avatar.getAttribute('data-affiliation');
            const verified = avatar.getAttribute('data-verified');
            const topics = avatar.getAttribute('data-topics');
            const photoSrc = avatar.src;

            if (!name) return;

            const authorPhoto = citeBox.querySelector('.cite-box-author-photo');
            const authorName = citeBox.querySelector('.cite-box-author-name');
            const authorAffiliation = citeBox.querySelector('.cite-box-author-affiliation');
            const authorVerified = citeBox.querySelector('.cite-box-author-verified');
            const authorTopics = citeBox.querySelector('.cite-box-author-topics');

            if (authorPhoto) authorPhoto.src = photoSrc;
            if (authorName) authorName.textContent = name;
            if (authorAffiliation) authorAffiliation.textContent = affiliation;
            if (authorVerified) authorVerified.innerHTML = verified;
            if (authorTopics) authorTopics.innerHTML = topics;

            // Phase 3: Reposition keeping this box focused
            requestAnimationFrame(() => alignMarginItems(citeBox));
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeAvatarHover);
