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

/**
 * Reference back-links: add numbered ↑ links from reference entries to every citation in text.
 */
document.addEventListener('DOMContentLoaded', function () {
    var refItems = document.querySelectorAll('ol li[id^="ref-"]');
    if (!refItems.length) return;

    var refsContainer = refItems[0].parentElement;
    var citationLinks = document.querySelectorAll('a[href^="#ref-"]');
    var allCitations = {};

    citationLinks.forEach(function (link) {
        if (refsContainer.contains(link)) return;
        var refId = link.getAttribute('href').substring(1);
        if (!allCitations[refId]) allCitations[refId] = [];
        var idx = allCitations[refId].length + 1;
        link.id = 'cite-' + refId + '-' + idx;
        allCitations[refId].push(link);
    });

    refItems.forEach(function (li) {
        var citations = allCitations[li.id];
        if (!citations || !citations.length) return;
        citations.forEach(function (cite, i) {
            var backLink = document.createElement('a');
            backLink.href = '#' + cite.id;
            backLink.className = 'ref-backlink';
            backLink.textContent = '\u2191' + (i + 1);
            backLink.title = 'Citation ' + (i + 1) + ' in text';
            li.appendChild(backLink);
        });
    });

    // Handle fragment scroll after dynamic IDs are created
    if (window.location.hash) {
        var target = document.querySelector(window.location.hash);
        if (target) {
            setTimeout(function () { target.scrollIntoView(); }, 100);
        }
    }
});
