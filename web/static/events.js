// Live updates from the server (see events.py).
//
//   Events.on('vote', function (data) { ... });   // handle an event
//   Events.reloadOn('new-game', 'new-player');     // just reload the page
//
// The stream URL comes from <body data-events-url="...">; it carries the id of
// the latest event at render time, so nothing published in between is lost. Pages without it
// get no live updates. Missed events are replayed after reconnecting; if that
// is impossible the server sends `resync` and the page reloads.
(function () {
    const handlers = {};
    let source = null;
    let lastId = '';
    const url = document.body.dataset.eventsUrl;

    function dispatch(type, e) {
        let data = null;
        try { data = JSON.parse(e.data); } catch (_) {}
        if (e.lastEventId) lastId = e.lastEventId;
        (handlers[type] || []).forEach(function (fn) { fn(data, e); });
    }

    function listen(type) {
        if (source) source.addEventListener(type, function (e) { dispatch(type, e); });
    }

    function withLastId(u, id) {
        const parsed = new URL(u, location.href);
        parsed.searchParams.set('last_id', id);
        return parsed.toString();
    }

    function connect() {
        if (!url) return;
        // The browser resends the last id itself on automatic reconnects;
        // this covers reconnects we start ourselves.
        source = new EventSource(lastId ? withLastId(url, lastId) : url);
        Object.keys(handlers).forEach(listen);
    }

    // A phone that slept may have a dead connection that the browser has
    // given up on; reconnect when the page becomes visible again.
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && source
                && source.readyState === EventSource.CLOSED) {
            source.close();
            connect();
        }
    });

    window.Events = {
        on: function (type, fn) {
            const isNew = !handlers[type];
            (handlers[type] = handlers[type] || []).push(fn);
            if (isNew) listen(type);
        },
        reloadOn: function () {
            for (const type of arguments) {
                window.Events.on(type, function () { location.reload(); });
            }
        },
    };
    window.Events.reloadOn('resync');
    connect();
})();
