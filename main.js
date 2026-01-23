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
 * Align side notes.
 */
function alignSidenotes() {
    if (window.matchMedia('(max-width: 1024px)').matches) return;

    document.querySelectorAll('.sidenote-ref').forEach((ref) => {
        const targetId = ref.getAttribute('href');
        if (!targetId || !targetId.startsWith('#')) return;

        const sidenote = document.querySelector(targetId);
        if (!sidenote) return;

        const block = ref.closest('.sidenote') || ref.closest('section');
        if (!block) return;

        const refRect = ref.getBoundingClientRect();
        const blockRect = block.getBoundingClientRect();

        const top = refRect.top - blockRect.top;

        sidenote.style.top = `${top}px`;
    });

    document.querySelectorAll('section').forEach((section) => {
        const sidenotes = Array.from(section.querySelectorAll('.sidenote'));

        if (sidenotes.length <= 1) return;

        const GAP = 12;

        sidenotes.sort((a, b) => {
            const topA = parseFloat(a.style.top) || 0;
            const topB = parseFloat(b.style.top) || 0;
            return topA - topB;
        });

        let lastBottom = -Infinity;

        sidenotes.forEach((sn) => {
            let top = parseFloat(sn.style.top) || 0;

            const height = sn.getBoundingClientRect().height;

            if (top < lastBottom + GAP) {
                top = lastBottom + GAP;
                sn.style.top = `${top}px`;
            }

            lastBottom = top + height;
        });
    });
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

// Cite-box positioning and hover highlighting
const MIN_BOX_GAP = 20; // Minimum pixels between boxes

function getCiteBoxData() {
    const boxes = Array.from(document.querySelectorAll('.cite-box[data-ref]'));
    return boxes.map(box => {
        const refId = box.getAttribute('data-ref');
        const ref = document.getElementById(refId);
        const wrapper = box.closest('.cite-box-wrapper');
        if (!ref || !wrapper) return null;

        const refRect = ref.getBoundingClientRect();
        const wrapperRect = wrapper.getBoundingClientRect();
        const targetTop = refRect.top - wrapperRect.top;

        return { box, ref, wrapper, targetTop, height: box.offsetHeight };
    }).filter(Boolean).sort((a, b) => a.targetTop - b.targetTop);
}

function positionCiteBoxes(focusedRefId = null) {
    const boxData = getCiteBoxData();
    if (boxData.length === 0) return;

    // Find the focused box index (if any)
    const focusedIndex = focusedRefId
        ? boxData.findIndex(d => d.ref.id === focusedRefId)
        : -1;

    if (focusedIndex >= 0) {
        // Position focused box at its ideal spot, shift others around it
        const focused = boxData[focusedIndex];
        const focusedTop = focused.targetTop;

        // Position focused box
        focused.box.style.top = `${focusedTop}px`;

        // Position boxes above the focused one (going upward)
        let nextBottom = focusedTop - MIN_BOX_GAP;
        for (let i = focusedIndex - 1; i >= 0; i--) {
            const item = boxData[i];
            const itemTop = Math.min(item.targetTop, nextBottom - item.height);
            item.box.style.top = `${itemTop}px`;
            nextBottom = itemTop - MIN_BOX_GAP;
        }

        // Position boxes below the focused one (going downward)
        let lastBottom = focusedTop + focused.height;
        for (let i = focusedIndex + 1; i < boxData.length; i++) {
            const item = boxData[i];
            const itemTop = Math.max(item.targetTop, lastBottom + MIN_BOX_GAP);
            item.box.style.top = `${itemTop}px`;
            lastBottom = itemTop + item.height;
        }
    } else {
        // Default positioning: collision avoidance from top
        let lastBottom = -Infinity;
        boxData.forEach(({ box, targetTop, height }) => {
            const adjustedTop = Math.max(targetTop, lastBottom + MIN_BOX_GAP);
            box.style.top = `${adjustedTop}px`;
            lastBottom = adjustedTop + height;
        });
    }
}

let activeCiteRef = null;
let resetTimeout = null;

function setActiveCite(refId) {
    if (resetTimeout) {
        clearTimeout(resetTimeout);
        resetTimeout = null;
    }
    // Clear previous highlights before setting new one
    if (activeCiteRef && activeCiteRef !== refId) {
        document.querySelectorAll('.cite-box.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
        document.querySelectorAll('.cite-box-ref.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
    }
    activeCiteRef = refId;
    positionCiteBoxes(refId);
}

function clearActiveCite() {
    // Delay to allow moving between citation and box
    resetTimeout = setTimeout(() => {
        activeCiteRef = null;
        positionCiteBoxes();
        // Remove all highlights
        document.querySelectorAll('.cite-box.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
        document.querySelectorAll('.cite-box-ref.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
    }, 10000);
}

function initializeCiteBoxes() {
    positionCiteBoxes();

    // Hover on box -> highlight citation and reposition
    document.querySelectorAll('.cite-box[data-ref]').forEach((box) => {
        const refId = box.getAttribute('data-ref');
        const ref = document.getElementById(refId);
        if (!ref) return;

        box.addEventListener('mouseenter', () => {
            // Only highlight, don't reposition
            if (resetTimeout) {
                clearTimeout(resetTimeout);
                resetTimeout = null;
            }
            // Clear other highlights first
            document.querySelectorAll('.cite-box.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            document.querySelectorAll('.cite-box-ref.is-highlighted').forEach(el => el.classList.remove('is-highlighted'));
            ref.classList.add('is-highlighted');
            box.classList.add('is-highlighted');
        });

        box.addEventListener('mouseleave', () => {
            // Only clear highlight if not actively focused from citation
            if (activeCiteRef !== refId) {
                ref.classList.remove('is-highlighted');
                box.classList.remove('is-highlighted');
            } else {
                clearActiveCite();
            }
        });
    });

    // Hover on citation -> highlight box and reposition
    document.querySelectorAll('.cite-box-ref[data-box]').forEach((ref) => {
        const boxId = ref.getAttribute('data-box');
        const box = document.getElementById(boxId);
        if (!box) return;

        ref.addEventListener('mouseenter', () => {
            setActiveCite(ref.id);
            box.classList.add('is-highlighted');
            ref.classList.add('is-highlighted');
        });

        ref.addEventListener('mouseleave', () => {
            clearActiveCite();
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeCiteBoxes);
window.addEventListener('load', () => positionCiteBoxes());
window.addEventListener('resize', () => positionCiteBoxes());
