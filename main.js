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
 * Align margin items (citation sidebar tracks).
 *
 * Phase 1 (read): measure each track's target top from its first visible
 *   card's anchor element.
 * Phase 2 (write): apply all top values in one batch (no interleaved reads).
 * Phase 3 (read): measure heights for overlap prevention.
 * Phase 4 (write): adjust tops to prevent overlaps.
 */
function alignMarginItems() {
    if (window.matchMedia('(max-width: 899px)').matches) return;

    var marginCol = document.querySelector('.margin-column');
    if (!marginCol) return;

    var marginColRect = marginCol.getBoundingClientRect();
    var trackEls = marginCol.querySelectorAll('.cite-sidebar-track');
    if (!trackEls.length) return;

    // Phase 1 (read): collect target tops
    var trackData = [];
    for (var i = 0; i < trackEls.length; i++) {
        var track = trackEls[i];
        var firstVisible = track.querySelector('.cite-sidebar-card:not(.is-hidden)');
        if (!firstVisible) { trackData.push(null); continue; }

        var anchorId = firstVisible.getAttribute('data-anchor-id');
        if (!anchorId) { trackData.push(null); continue; }
        var anchor = document.getElementById(anchorId);
        if (!anchor) { trackData.push(null); continue; }

        var anchorRect = anchor.getBoundingClientRect();
        trackData.push({ el: track, top: anchorRect.top - marginColRect.top });
    }

    // Phase 2 (write): apply tops
    for (var j = 0; j < trackData.length; j++) {
        if (trackData[j]) trackData[j].el.style.top = trackData[j].top + 'px';
    }

    // Phase 3 (read): measure heights for overlap prevention
    var items = [];
    for (var k = 0; k < trackData.length; k++) {
        if (!trackData[k]) continue;
        items.push({
            el: trackData[k].el,
            top: trackData[k].top,
            height: trackData[k].el.getBoundingClientRect().height
        });
    }

    if (items.length <= 1) return;

    items.sort(function (a, b) { return a.top - b.top; });

    // Phase 4 (write): push down overlapping tracks
    var GAP = 12;
    var lastBottom = -Infinity;
    for (var m = 0; m < items.length; m++) {
        var it = items[m];
        if (it.top < lastBottom + GAP) {
            it.top = lastBottom + GAP;
            it.el.style.top = it.top + 'px';
        }
        lastBottom = it.top + it.height;
    }
}

// Expose for citation-card.js
window.realignMarginItems = alignMarginItems;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', alignMarginItems);
} else {
    alignMarginItems();
}

window.addEventListener('load', alignMarginItems);

if (document.fonts) {
    document.fonts.ready.then(alignMarginItems);
}

window.addEventListener('resize', alignMarginItems);

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
