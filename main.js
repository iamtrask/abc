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
 * Unified positioning for sidenotes and cite-boxes.
 */
const MARGIN_GAP = 16;

function getMarginItemTargetTop(item) {
    if (item.classList.contains('sidenote')) {
        const refSelector = `a[href="#${item.id}"]`;
        const ref = document.querySelector(refSelector);
        if (!ref) return parseFloat(item.style.top) || 0;

        const section = ref.closest('section');
        if (!section) return parseFloat(item.style.top) || 0;

        const refRect = ref.getBoundingClientRect();
        const sectionRect = section.getBoundingClientRect();
        return refRect.top - sectionRect.top;
    } else if (item.classList.contains('cite-box')) {
        const refId = item.getAttribute('data-ref');
        const ref = document.getElementById(refId);
        if (!ref) return parseFloat(item.style.top) || 0;

        const wrapper = item.closest('.cite-box-wrapper');
        if (!wrapper) return parseFloat(item.style.top) || 0;

        const refRect = ref.getBoundingClientRect();
        const wrapperRect = wrapper.getBoundingClientRect();
        return refRect.top - wrapperRect.top;
    }
    return 0;
}

function alignAllMarginItems(fixedItem = null) {
    if (window.matchMedia('(max-width: 1024px)').matches) return;

    // Collect all margin items (sidenotes and cite-boxes) within each section
    document.querySelectorAll('section').forEach((section) => {
        const sidenotes = Array.from(section.querySelectorAll('.sidenote'));
        const citeBoxWrapper = section.querySelector('.cite-box-wrapper');
        const citeBoxes = citeBoxWrapper ? Array.from(citeBoxWrapper.querySelectorAll('.cite-box')) : [];

        const allItems = [...sidenotes, ...citeBoxes];
        if (allItems.length === 0) return;

        // Calculate target tops and collect data
        const itemData = allItems.map(item => ({
            item,
            targetTop: getMarginItemTargetTop(item),
            height: item.offsetHeight,
            isFixed: item === fixedItem
        }));

        // Sort by target top position
        itemData.sort((a, b) => a.targetTop - b.targetTop);

        // Find fixed item index if any
        const fixedIndex = itemData.findIndex(d => d.isFixed);

        if (fixedIndex >= 0) {
            // Keep fixed item in place, adjust others around it
            const fixed = itemData[fixedIndex];
            const fixedTop = parseFloat(fixed.item.style.top) || fixed.targetTop;

            // Position items above fixed (going upward)
            let nextBottom = fixedTop - MARGIN_GAP;
            for (let i = fixedIndex - 1; i >= 0; i--) {
                const d = itemData[i];
                const itemTop = Math.min(d.targetTop, nextBottom - d.height);
                d.item.style.top = `${Math.max(0, itemTop)}px`;
                nextBottom = Math.max(0, itemTop) - MARGIN_GAP;
            }

            // Position items below fixed (going downward)
            let lastBottom = fixedTop + fixed.height;
            for (let i = fixedIndex + 1; i < itemData.length; i++) {
                const d = itemData[i];
                const itemTop = Math.max(d.targetTop, lastBottom + MARGIN_GAP);
                d.item.style.top = `${itemTop}px`;
                lastBottom = itemTop + d.height;
            }
        } else {
            // Standard collision avoidance from top
            let lastBottom = -Infinity;
            itemData.forEach(({ item, targetTop, height }) => {
                const adjustedTop = Math.max(targetTop, lastBottom + MARGIN_GAP);
                item.style.top = `${adjustedTop}px`;
                lastBottom = adjustedTop + height;
            });
        }
    });
}

// Legacy function name for compatibility
function alignSidenotes() {
    alignAllMarginItems();
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

function positionCiteBoxes(focusedRefId = null) {
    // Use unified positioning
    alignAllMarginItems();
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

            // Reposition all margin items after content change, keeping this one fixed
            requestAnimationFrame(() => alignAllMarginItems(citeBox));
        });
    });
}

document.addEventListener('DOMContentLoaded', initializeAvatarHover);
