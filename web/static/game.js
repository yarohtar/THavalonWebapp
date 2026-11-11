// Live game panels: sends actions and refreshes on 'game-update' events.
//
// The page has an element with data-panels-url (GET: JSON of panel HTML)
// and optionally data-action-url (POST target for <form class="game-action">
// without its own action attribute). Panels are elements with
// data-panel="<name>"; the JSON maps each name to its new HTML.
(function () {
    const root = document.querySelector('[data-panels-url]');
    if (!root) return;
    const panelsUrl = root.dataset.panelsUrl;
    const actionUrl = root.dataset.actionUrl;

    // Identifies a checkbox/radio across re-renders: its form (by target
    // and hidden fields) plus its own name and value.
    function inputKey(input) {
        const form = input.form;
        let key = form ? (form.getAttribute('action') || '') : '';
        if (form) form.querySelectorAll('input[type=hidden]').forEach(function (h) {
            key += '|' + h.name + '=' + h.value;
        });
        return key + '|' + input.name + '=' + input.value;
    }

    function render(panels) {
        for (const name in panels) {
            const el = document.querySelector('[data-panel="' + name + '"]');
            if (!el) continue;
            // Keep open <details> (e.g. "This game") open across refreshes.
            const open = Array.from(el.querySelectorAll('details[open] > summary'))
                .map(function (s) { return s.textContent; });
            // Keep half-made choices (players ticked for a team) too.
            const picks = new Map();
            el.querySelectorAll('.pick input').forEach(function (i) {
                picks.set(inputKey(i), i.checked);
            });
            el.innerHTML = panels[name];
            el.querySelectorAll('details > summary').forEach(function (s) {
                if (open.indexOf(s.textContent) >= 0) s.parentElement.open = true;
            });
            el.querySelectorAll('.pick input').forEach(function (i) {
                const key = inputKey(i);
                if (picks.has(key)) i.checked = picks.get(key);
            });
            el.querySelectorAll('.team-picker').forEach(updatePicker);
        }
        document.dispatchEvent(new CustomEvent('panels-rendered'));
    }

    let refreshing = null;
    function refresh() {
        if (refreshing) return refreshing;
        refreshing = fetch(panelsUrl, {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) { if (d) render(d); })
            .finally(function () { refreshing = null; });
        return refreshing;
    }

    function toast(message) {
        let t = document.getElementById('game-toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'game-toast';
            t.className = 'game-toast';
            document.body.appendChild(t);
        }
        t.textContent = message;
        t.classList.add('show');
        clearTimeout(t._timer);
        t._timer = setTimeout(function () { t.classList.remove('show'); }, 3500);
    }

    // Remember which button submitted the form (FormData's submitter
    // argument isn't available on older phones).
    let lastSubmitter = null;
    document.addEventListener('click', function (e) {
        const b = e.target.closest('form.game-action button[type=submit]');
        if (b) lastSubmitter = b;
    }, true);

    let busy = false;
    document.addEventListener('submit', function (e) {
        const form = e.target.closest('form.game-action');
        if (!form) return;
        e.preventDefault();
        if (busy) return;
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        const data = new FormData(form);
        const b = e.submitter || lastSubmitter;
        if (b && b.name && form.contains(b)) data.set(b.name, b.value);
        busy = true;
        fetch(form.getAttribute('action') || actionUrl,
              {method: 'POST', body: data, credentials: 'same-origin'})
            .then(function (r) {
                return r.json().catch(function () { return {}; }).then(function (d) {
                    if (r.ok) render(d);
                    else toast(d.error || 'Something went wrong.');
                });
            })
            .catch(function () { toast('No connection. Try again.'); })
            .finally(function () { busy = false; });
    });

    // Team pickers: show "n / size" and only allow sending a full team.
    function updatePicker(form) {
        const box = form.querySelector('[data-team-size]');
        const size = +box.dataset.teamSize;
        const n = form.querySelectorAll('input[name=team]:checked').length;
        const button = form.querySelector('button[type=submit]');
        button.disabled = n !== size;
        button.textContent = button.dataset.label + ' (' + n + '/' + size + ')';
    }
    document.addEventListener('change', function (e) {
        const form = e.target.closest('.team-picker');
        if (form) updatePicker(form);
    });
    document.querySelectorAll('.team-picker').forEach(updatePicker);

    Events.on('game-update', refresh);
    // After a phone wakes up, make sure we show the latest state.
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') refresh();
    });
})();
