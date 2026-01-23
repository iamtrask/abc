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
 * Handles both sidenotes and cite-boxes with collision avoidance across sections.
 */
const MARGIN_GAP = 20;

function positionMarginItemsGlobal(items, focusedItem = null) {
    if (items.length === 0) return;

    const main = document.querySelector('main') || document.body;
    const mainRect = main.getBoundingClientRect();
    const scrollTop = window.scrollY;

    // Calculate target positions (relative to main element)
    items.forEach(item => {
        if (item.refElement) {
            const refRect = item.refElement.getBoundingClientRect();
            // Get the section containing this item for positioning context
            const section = item.element.closest('section');
            const sectionRect = section ? section.getBoundingClientRect() : mainRect;
            // Store both global target (for sorting) and section-relative (for positioning)
            item.globalTarget = refRect.top + scrollTop;
            item.sectionOffset = sectionRect.top + scrollTop;
            item.targetTop = refRect.top - sectionRect.top;
        }
        // Refresh height in case content changed
        item.height = item.element.offsetHeight;
    });

    // Sort by global target position
    items.sort((a, b) => a.globalTarget - b.globalTarget);

    // Focus-aware positioning: focused item gets priority, others shift around it
    const focusedIndex = focusedItem ? items.indexOf(focusedItem) : -1;

    if (focusedIndex >= 0) {
        const focused = items[focusedIndex];

        // Calculate space needed for items above (in global coordinates)
        let spaceNeededAbove = 0;
        for (let i = 0; i < focusedIndex; i++) {
            spaceNeededAbove += items[i].height + MARGIN_GAP;
        }

        // Position focused item - push down if items above need more space
        const focusedGlobalTop = Math.max(focused.globalTarget, spaceNeededAbove);
        const focusedLocalTop = focusedGlobalTop - focused.sectionOffset;
        focused.element.style.top = `${focusedLocalTop}px`;
        focused.currentGlobalTop = focusedGlobalTop;

        // Position items above (push up from focused item)
        let ceiling = focusedGlobalTop - MARGIN_GAP;
        for (let i = focusedIndex - 1; i >= 0; i--) {
            const item = items[i];
            const idealGlobalTop = item.globalTarget;
            const globalTop = Math.min(idealGlobalTop, ceiling - item.height);
            const clampedGlobalTop = Math.max(0, globalTop);
            const localTop = clampedGlobalTop - item.sectionOffset;
            item.element.style.top = `${localTop}px`;
            item.currentGlobalTop = clampedGlobalTop;
            ceiling = clampedGlobalTop - MARGIN_GAP;
        }

        // Position items below (push down if needed)
        let floor = focusedGlobalTop + focused.height + MARGIN_GAP;
        for (let i = focusedIndex + 1; i < items.length; i++) {
            const item = items[i];
            const idealGlobalTop = item.globalTarget;
            const globalTop = Math.max(idealGlobalTop, floor);
            const localTop = globalTop - item.sectionOffset;
            item.element.style.top = `${localTop}px`;
            item.currentGlobalTop = globalTop;
            floor = globalTop + item.height + MARGIN_GAP;
        }
    } else {
        // No focus: simple top-down collision avoidance
        let lastGlobalBottom = -Infinity;
        items.forEach(item => {
            const idealGlobalTop = item.globalTarget;
            const globalTop = Math.max(idealGlobalTop, lastGlobalBottom + MARGIN_GAP);
            const localTop = globalTop - item.sectionOffset;
            item.element.style.top = `${localTop}px`;
            lastGlobalBottom = globalTop + item.height;
        });
    }
}

// Track focused margin item for hover behavior
let focusedMarginElement = null;
let focusResetTimeout = null;

/**
 * Collect all margin items from the entire document.
 */
function collectAllMarginItems() {
    const main = document.querySelector('main') || document.body;
    const sidenotes = Array.from(main.querySelectorAll('.sidenote'));
    const citeBoxes = Array.from(main.querySelectorAll('.cite-box[data-ref]'));

    const sidenoteItems = sidenotes.map(element => ({
        element,
        type: 'sidenote',
        refElement: document.querySelector(`a[href="#${element.id}"]`),
        targetTop: 0,
        height: element.offsetHeight
    }));

    const citeBoxItems = citeBoxes.map(element => {
        const refId = element.getAttribute('data-ref');
        return {
            element,
            type: 'cite-box',
            refElement: document.getElementById(refId),
            targetTop: 0,
            height: element.offsetHeight
        };
    });

    return [...sidenoteItems, ...citeBoxItems];
}

/**
 * Align margin items using unified positioning system.
 * @param {HTMLElement|null} focusedElement - Element to focus (gets priority positioning)
 */
function alignMarginItems(focusedElement = null) {
    if (window.matchMedia('(max-width: 1024px)').matches) return;

    const items = collectAllMarginItems();
    const focusedItem = focusedElement
        ? items.find(item => item.element === focusedElement)
        : null;
    positionMarginItemsGlobal(items, focusedItem);
}

/**
 * Align all margin items (sidenotes + cards) using unified positioning system.
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

// Cite-box hover highlighting and focus positioning
function initializeCiteBoxes() {

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
            }, 2000);
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
            }, 2000);
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeCiteBoxes);

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

            // Only reposition if this card is already focused (don't steal focus)
            if (focusedMarginElement === citeBox) {
                requestAnimationFrame(() => alignMarginItems(citeBox));
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeAvatarHover);

// Click handlers for paper and author links
function initializeCiteBoxLinks() {
    // Track current scholar URL for author section
    document.querySelectorAll('.cite-box').forEach((citeBox) => {
        // Store the first author's scholar URL as default
        const firstAvatar = citeBox.querySelector('.cite-box-avatars img[data-scholar-url]');
        if (firstAvatar) {
            citeBox.dataset.currentScholarUrl = firstAvatar.getAttribute('data-scholar-url');
        }
    });

    // Update scholar URL when hovering avatars
    document.querySelectorAll('.cite-box-avatars img').forEach((avatar) => {
        avatar.addEventListener('mouseenter', () => {
            const citeBox = avatar.closest('.cite-box');
            const scholarUrl = avatar.getAttribute('data-scholar-url');
            if (citeBox && scholarUrl) {
                citeBox.dataset.currentScholarUrl = scholarUrl;
            }
        });

        // Click avatar to go to their Google Scholar
        avatar.addEventListener('click', (e) => {
            const scholarUrl = avatar.getAttribute('data-scholar-url');
            if (scholarUrl) {
                window.open(scholarUrl, '_blank');
            }
        });
    });

    // Click paper section to go to paper
    document.querySelectorAll('.cite-box-paper').forEach((paperSection) => {
        paperSection.addEventListener('click', () => {
            const citeBox = paperSection.closest('.cite-box');
            const paperUrl = citeBox?.getAttribute('data-paper-url');
            if (paperUrl) {
                window.open(paperUrl, '_blank');
            }
        });
    });

    // Click author section to go to current author's Google Scholar
    document.querySelectorAll('.cite-box-author').forEach((authorSection) => {
        authorSection.addEventListener('click', () => {
            const citeBox = authorSection.closest('.cite-box');
            const scholarUrl = citeBox?.dataset.currentScholarUrl;
            if (scholarUrl) {
                window.open(scholarUrl, '_blank');
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeCiteBoxLinks);

// Check if we're in modal mode by seeing if margin items are hidden by CSS
function isModalMode() {
    // Check if a cite-box or sidenote is hidden (visibility: hidden from CSS)
    const testItem = document.querySelector('.cite-box') || document.querySelector('.sidenote');
    if (!testItem) return false;
    const style = window.getComputedStyle(testItem);
    return style.visibility === 'hidden';
}

function openMarginModal(element, refElement) {
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

        // Close on overlay click (but not modal content)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeMarginModal();
        });

        // Close button
        overlay.querySelector('.margin-item-modal-close').addEventListener('click', closeMarginModal);
    }

    // Clone content into modal
    const content = overlay.querySelector('.margin-item-modal-content');
    content.innerHTML = '';
    const clone = element.cloneNode(true);
    clone.style.cssText = 'position:static !important; visibility:visible !important; left:auto !important;';
    content.appendChild(clone);

    // Set up avatar hover in cloned content
    clone.querySelectorAll('.cite-box-avatars img').forEach((avatar) => {
        avatar.addEventListener('mouseenter', () => {
            const name = avatar.getAttribute('data-name');
            const affiliation = avatar.getAttribute('data-affiliation');
            const verified = avatar.getAttribute('data-verified');
            const topics = avatar.getAttribute('data-topics');
            const photoSrc = avatar.src;

            if (!name) return;

            const authorPhoto = clone.querySelector('.cite-box-author-photo');
            const authorName = clone.querySelector('.cite-box-author-name');
            const authorAffiliation = clone.querySelector('.cite-box-author-affiliation');
            const authorVerified = clone.querySelector('.cite-box-author-verified');
            const authorTopics = clone.querySelector('.cite-box-author-topics');

            if (authorPhoto) authorPhoto.src = photoSrc;
            if (authorName) authorName.textContent = name;
            if (authorAffiliation) authorAffiliation.textContent = affiliation;
            if (authorVerified) authorVerified.innerHTML = verified;
            if (authorTopics) authorTopics.innerHTML = topics;
        });
    });

    overlay.classList.add('is-active');
    refElement?.classList.add('is-highlighted');

    // Store for cleanup
    overlay.dataset.activeItemId = element.id;
    overlay.dataset.activeRefId = refElement?.id || '';
}

function closeMarginModal() {
    const overlay = document.querySelector('.margin-item-modal-overlay');
    if (!overlay) return;

    overlay.classList.remove('is-active');

    // Remove highlight from ref
    const refId = overlay.dataset.activeRefId;
    if (refId) {
        document.getElementById(refId)?.classList.remove('is-highlighted');
    }

    // Also try data-ref for cite-boxes
    const itemId = overlay.dataset.activeItemId;
    if (itemId) {
        const item = document.getElementById(itemId);
        if (item?.classList.contains('sidenote')) {
            document.querySelector(`a[href="#${itemId}"]`)?.classList.remove('is-highlighted');
        }
    }
}

// Click handlers - prevent default scroll, open modal only on narrow screens
document.addEventListener('click', (e) => {
    // Check if clicked a sidenote ref
    const sidenoteRef = e.target.closest('.sidenote-ref');
    if (sidenoteRef) {
        e.preventDefault();
        e.stopPropagation();
        // Only open modal if items are hidden (narrow screen)
        if (isModalMode()) {
            const targetId = sidenoteRef.getAttribute('href');
            const sidenote = document.querySelector(targetId);
            if (sidenote) {
                openMarginModal(sidenote, sidenoteRef);
            }
        }
        return;
    }

    // Check if clicked a cite-box ref
    const citeRef = e.target.closest('.cite-box-ref');
    if (citeRef) {
        e.preventDefault();
        e.stopPropagation();
        // Only open modal if items are hidden (narrow screen)
        if (isModalMode()) {
            const boxId = citeRef.getAttribute('data-box');
            const box = document.getElementById(boxId);
            if (box) {
                openMarginModal(box, citeRef);
            }
        }
        return;
    }
}, true); // Use capture phase

// Escape to close modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMarginModal();
});
