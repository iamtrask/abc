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
        const OFFSET = 120;

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
}

function initializeSidenotes() {
    resizeSidenotes();
    alignSidenotes();
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
