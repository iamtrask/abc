/**
 * Citation sidebar cards — Google Comments style.
 *
 * Creates always-visible cards in the right margin for each unique citation
 * per section. Cards share space with sidenotes using unified overlap
 * prevention (alignMarginItems in main.js).
 *
 * - Default: compact (title + avatar row), faded/grayscale
 * - Hover cite link OR card: expand with full title, meta, author detail
 * - Section-based visibility via IntersectionObserver
 * - Snap-to-view: if card is off-screen when cite is hovered, temporarily
 *   fix it in the viewport
 *
 * Security: all text inserted via textContent or DOM methods.
 * Data comes from local JSON files.
 */
(function () {
    'use strict';

    /* ---- config ---- */
    var MAX_AV = 5;

    /* ---- state ---- */
    var chapterMap, refs, auths;
    var ready = false;
    var chapter = '';
    var cards = [];         // all created card elements
    var tracks = [];        // all created track containers
    var citeToCard = {};    // "sectionIndex:refNum" → card element

    /* ---- helpers ---- */

    function pageSlug() {
        var f = location.pathname.split('/').pop() || '';
        return f.replace('.html', '') || 'index';
    }

    function stripBraces(s) { return s ? s.replace(/[{}]/g, '') : ''; }

    function trimTo(s, n) {
        var c = stripBraces(s);
        if (c.length <= n) return c;
        var i = c.lastIndexOf(' ', n);
        return c.slice(0, i > n / 2 ? i : n) + '\u2026';
    }

    function hs(key) {
        var a = auths[key];
        return (a && a.headshot) || 'assets/headshots/default.svg';
    }

    function lookup(href) {
        if (!ready) return null;
        var m = chapterMap[chapter];
        if (!m) return null;
        if (!href || href.indexOf('#ref-') !== 0) return null;
        var k = m[href.slice(5)];
        return k && refs[k] ? { key: k, d: refs[k] } : null;
    }

    function refNumFromHref(href) {
        if (!href || href.indexOf('#ref-') !== 0) return null;
        return href.slice(5);
    }

    /* ---- data loading ---- */

    function load() {
        return Promise.all([
            fetch('data/chapter-map.json').then(function (r) { return r.json(); }),
            fetch('data/references.json').then(function (r) { return r.json(); }),
            fetch('data/authors.json').then(function (r) { return r.json(); })
        ]).then(function (d) {
            chapterMap = d[0]; refs = d[1]; auths = d[2];
            chapter = pageSlug();
            ready = true;
        }).catch(function () {});
    }

    /* ---- DOM builders ---- */

    function buildAuthorDetail(key) {
        var a = auths[key];
        if (!a) return null;

        var row = document.createElement('div');
        row.className = 'cite-sidebar-detail-row';

        var photo = document.createElement('img');
        photo.className = 'cite-sidebar-detail-photo';
        photo.src = hs(key);
        photo.alt = '';
        row.appendChild(photo);

        var info = document.createElement('div');
        info.className = 'cite-sidebar-detail-info';

        var nameEl = document.createElement('div');
        nameEl.className = 'cite-sidebar-detail-name';
        nameEl.textContent = a.displayName || key;
        info.appendChild(nameEl);

        if (a.affiliation) {
            var afEl = document.createElement('div');
            afEl.className = 'cite-sidebar-detail-affil';
            afEl.textContent = a.affiliation;
            info.appendChild(afEl);
        }

        var links = a.links || {};
        var lk = [];
        if (links.googleScholar) lk.push({ url: links.googleScholar, label: 'Scholar' });
        if (links.homepage) lk.push({ url: links.homepage, label: 'Homepage' });

        if (lk.length) {
            var linksEl = document.createElement('div');
            linksEl.className = 'cite-sidebar-detail-links';
            for (var i = 0; i < lk.length; i++) {
                var link = document.createElement('a');
                link.href = lk[i].url;
                link.target = '_blank';
                link.rel = 'noopener';
                link.textContent = lk[i].label;
                linksEl.appendChild(link);
            }
            info.appendChild(linksEl);
        }

        row.appendChild(info);
        return row;
    }

    function buildCard(r) {
        var d = r.d;
        var card = document.createElement('div');
        card.className = 'cite-sidebar-card is-hidden';

        // Title
        var titleDiv = document.createElement('div');
        titleDiv.className = 'cite-sidebar-title';
        var title = stripBraces(d.title || '');
        if (d.url) {
            var titleLink = document.createElement('a');
            titleLink.href = d.url;
            titleLink.target = '_blank';
            titleLink.rel = 'noopener';
            titleLink.textContent = title;
            titleDiv.appendChild(titleLink);
        } else {
            titleDiv.textContent = title;
        }
        card.appendChild(titleDiv);

        // Meta (year + venue) — strip LaTeX \url prefixes from venue
        var year = d.year || '';
        var rawVenue = d.venueShort || d.venue || '';
        if (rawVenue.indexOf('\\url') === 0) rawVenue = '';
        var venue = trimTo(rawVenue, 48);
        if (year || venue) {
            var meta = document.createElement('div');
            meta.className = 'cite-sidebar-meta';
            var parts = [];
            if (year) parts.push(String(year));
            if (venue) parts.push(venue);
            meta.textContent = parts.join(' \u00B7 ');
            card.appendChild(meta);
        }

        // Author avatars
        var ak = d.authors || [];
        if (ak.length) {
            var avatars = document.createElement('div');
            avatars.className = 'cite-sidebar-avatars';
            var n = Math.min(ak.length, MAX_AV);
            for (var i = 0; i < n; i++) {
                var a = auths[ak[i]];
                var nm = a ? a.displayName : ak[i];
                var av = document.createElement('div');
                av.className = 'cite-sidebar-av';
                av.setAttribute('data-ak', ak[i]);
                av.title = nm;
                var img = document.createElement('img');
                img.src = hs(ak[i]);
                img.alt = '';
                av.appendChild(img);
                avatars.appendChild(av);
            }
            if (ak.length > MAX_AV) {
                var more = document.createElement('div');
                more.className = 'cite-sidebar-av-more';
                more.textContent = '+' + (ak.length - MAX_AV);
                avatars.appendChild(more);
            }
            card.appendChild(avatars);

            // Author detail panel (populated on avatar hover)
            var detail = document.createElement('div');
            detail.className = 'cite-sidebar-detail';
            card.appendChild(detail);
        }

        return card;
    }

    /* ---- avatar hover ---- */

    function activateAvatar(av, card) {
        var allAv = card.querySelectorAll('.cite-sidebar-av');
        for (var i = 0; i < allAv.length; i++) allAv[i].classList.remove('is-active');
        av.classList.add('is-active');

        var detail = card.querySelector('.cite-sidebar-detail');
        if (!detail) return;

        while (detail.firstChild) detail.removeChild(detail.firstChild);
        var row = buildAuthorDetail(av.getAttribute('data-ak'));
        if (row) {
            detail.appendChild(row);
            detail.classList.add('is-visible');
        }
    }

    function wireAvatarHovers(card) {
        var avs = card.querySelectorAll('.cite-sidebar-av');
        for (var i = 0; i < avs.length; i++) {
            (function (av) {
                av.addEventListener('mouseenter', function () {
                    activateAvatar(av, card);
                });
            })(avs[i]);
        }
        // Show first author by default when card is highlighted
        if (avs.length) {
            var detail = card.querySelector('.cite-sidebar-detail');
            if (detail) activateAvatar(avs[0], card);
        }
    }

    /* ---- highlight logic ---- */

    var unhighlightTimer = null;
    var activeEntry = null;   // currently highlighted { card, citeLinks, track }

    function cancelUnhighlight() {
        if (unhighlightTimer) {
            clearTimeout(unhighlightTimer);
            unhighlightTimer = null;
        }
    }

    /** Apply translateY to a track container (shifts all its cards as a unit). */
    function applySidebarOffset(track, dy) {
        if (!track) return;
        track.style.transform = dy ? 'translateY(' + dy + 'px)' : '';
    }

    function doUnhighlight() {
        if (!activeEntry) return;
        activeEntry.card.classList.remove('is-highlighted');
        activeEntry.card.classList.remove('is-expanded');
        for (var i = 0; i < activeEntry.citeLinks.length; i++) {
            activeEntry.citeLinks[i].classList.remove('is-card-highlight');
        }
        applySidebarOffset(activeEntry.track, 0);
        activeEntry = null;
    }

    function scheduleUnhighlight() {
        cancelUnhighlight();
        unhighlightTimer = setTimeout(doUnhighlight, 400);
    }

    /** Highlight from cite hover — shift track so card aligns with cite */
    function highlightFromCite(entry, cite) {
        cancelUnhighlight();
        if (activeEntry === entry) return;
        if (activeEntry) doUnhighlight();
        activeEntry = entry;

        entry.card.classList.remove('is-hidden');
        entry.card.classList.add('is-highlighted');
        for (var i = 0; i < entry.citeLinks.length; i++) {
            entry.citeLinks[i].classList.add('is-card-highlight');
        }

        // Shift the track so this card aligns with the hovered cite
        var citeRect = cite.getBoundingClientRect();
        var cardRect = entry.card.getBoundingClientRect();
        applySidebarOffset(entry.track, citeRect.top - cardRect.top);
    }

    /** Highlight from card hover — expand to show author detail; flex flow handles pushing */
    function highlightFromCard(entry) {
        cancelUnhighlight();
        if (activeEntry === entry) {
            // Already highlighted from cite hover — just expand it
            entry.card.classList.add('is-expanded');
            return;
        }
        if (activeEntry) doUnhighlight();
        activeEntry = entry;

        entry.card.classList.add('is-highlighted');
        entry.card.classList.add('is-expanded');
        for (var i = 0; i < entry.citeLinks.length; i++) {
            entry.citeLinks[i].classList.add('is-card-highlight');
        }
    }

    /* ---- card creation ---- */

    function createCards() {
        if (!ready) return;

        var allSections = document.querySelectorAll('main > section:not(.references)');
        var sectionIndex = 0;

        allSections.forEach(function (section) {
            var cites = section.querySelectorAll('a.cite');
            var seenRefs = {};  // refNum → { card, citeLinks[], track }
            var sectionCards = [];

            cites.forEach(function (cite) {
                var href = cite.getAttribute('href');
                var refNum = refNumFromHref(href);
                if (!refNum) return;

                var r = lookup(href);
                if (!r) return;

                var mapKey = sectionIndex + ':' + refNum;

                if (seenRefs[refNum]) {
                    // Deduplicate: link this cite to the existing card
                    seenRefs[refNum].citeLinks.push(cite);
                    citeToCard[cite.id || (cite.id = 'cite-sc-' + sectionIndex + '-' + refNum + '-' + seenRefs[refNum].citeLinks.length)] = seenRefs[refNum];
                    return;
                }

                // Create a new card
                var card = buildCard(r);
                wireAvatarHovers(card);

                // Assign a unique anchor ID to the first cite for positioning
                if (!cite.id) cite.id = 'cite-anchor-' + sectionIndex + '-' + refNum;
                card.setAttribute('data-anchor-id', cite.id);
                card.setAttribute('data-ref-num', refNum);
                card.setAttribute('data-section-index', String(sectionIndex));

                sectionCards.push(card);
                cards.push(card);

                var entry = { card: card, citeLinks: [cite], track: null };
                seenRefs[refNum] = entry;
                citeToCard[mapKey] = entry;

                // Card hover → expand to show author detail
                card.addEventListener('mouseenter', function () {
                    highlightFromCard(entry);
                });
                card.addEventListener('mouseleave', function () {
                    scheduleUnhighlight();
                });
            });

            // Create one track container per section and append all cards to it
            if (sectionCards.length) {
                var track = document.createElement('div');
                track.className = 'cite-sidebar-track';
                for (var i = 0; i < sectionCards.length; i++) {
                    track.appendChild(sectionCards[i]);
                }
                section.appendChild(track);
                tracks.push(track);

                // Store track reference in each entry
                Object.keys(seenRefs).forEach(function (refNum) {
                    seenRefs[refNum].track = track;
                });
            }

            // Cite hover → highlight card + shift sidebar
            Object.keys(seenRefs).forEach(function (refNum) {
                var entry = seenRefs[refNum];
                entry.citeLinks.forEach(function (cite) {
                    cite.addEventListener('mouseenter', function () {
                        highlightFromCite(entry, cite);
                    });
                    cite.addEventListener('mouseleave', function () {
                        scheduleUnhighlight();
                    });
                });
            });

            sectionIndex++;
        });

    }

    /* ---- IntersectionObserver: show/hide cards by anchor cite proximity ---- */

    function setupObserver() {
        var realignQueued = false;
        function queueRealign() {
            if (realignQueued) return;
            realignQueued = true;
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    realignQueued = false;
                    if (window.realignMarginItems) window.realignMarginItems();
                });
            });
        }

        // Observe each card's anchor cite element.
        // Only show cards whose anchor is near the viewport.
        var observer = new IntersectionObserver(function (entries) {
            var changed = false;
            entries.forEach(function (entry) {
                var card = entry.target._sidebarCard;
                if (!card) return;

                if (entry.isIntersecting) {
                    if (card.classList.contains('is-hidden')) {
                        card.classList.remove('is-hidden');
                        changed = true;
                    }
                } else {
                    if (!card.classList.contains('is-hidden')) {
                        card.classList.add('is-hidden');
                        card.classList.remove('is-highlighted');
                        changed = true;
                    }
                }
            });

            if (changed) queueRealign();
        }, {
            // Show cards when their anchor is within ~half a viewport of the edges
            rootMargin: '50% 0px 50% 0px',
            threshold: 0
        });

        // Wire each card's anchor cite to the observer
        cards.forEach(function (card) {
            var anchorId = card.getAttribute('data-anchor-id');
            if (!anchorId) return;
            var anchor = document.getElementById(anchorId);
            if (!anchor) return;
            anchor._sidebarCard = card;
            observer.observe(anchor);
        });
    }

    /* ---- init ---- */

    function init() {
        var pg = pageSlug();
        if (pg === 'references' || pg === 'about') return;

        // Only show sidebar cards on wide screens
        if (window.innerWidth < 1400) return;

        createCards();
        setupObserver();

        // Re-layout on resize; hide cards if screen becomes narrow
        window.addEventListener('resize', function () {
            if (window.innerWidth < 1400) {
                cards.forEach(function (card) {
                    card.classList.add('is-hidden');
                });
            } else {
                // Trigger observer re-evaluation by re-laying out
                if (window.realignMarginItems) window.realignMarginItems();
            }
        }, { passive: true });
    }

    load().then(function () {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }
    });
})();
