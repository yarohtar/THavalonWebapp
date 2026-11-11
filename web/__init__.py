"""The THavalon website: players' phones and the host's page around the
game engine (the thavalon package).

    app           the Flask app: settings, who is asking, everything plugged in
    routes/       the pages: player, host, play (live game requests), rules
    lobbies       open games and who joined them (stored in Redis)
    games         a lobby's game: settings, deal, role info, the controller
    host_settings the host's saved preferences and the rules editor's layout
    host_votes    votes the host starts by hand (fallback, outside the game)
    panels        rendering a game's live panels and role page
    visitor       this browser's lobby and game
    rules/        rules pages, notes on changed rules, role rule texts
    store         Redis storage (pickles, atomic updates)
    events        live updates to browsers (Server-Sent Events)
    access        Cloudflare Access tokens
    admin, dev    admin pages; test scenarios (dev site only)

    templates/, static/   pages, styles and scripts
"""
