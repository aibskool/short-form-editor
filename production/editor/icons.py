"""Original stroke icons (24x24 grid) for motion graphics. No brand logos.

Brand marks must come from user-supplied image files; these glyphs are generic.
"""

_PATHS = {
    "chat": '<path d="M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17.5H4A1.5 1.5 0 0 1 2.5 16V7A1.5 1.5 0 0 1 4 5.5z"/><path d="M7 10.5h10M7 13.5h6"/>',
    "mail": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M3.5 6.5l8.5 6.5 8.5-6.5"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4M7.5 13.5h3v3h-3z"/>',
    "bolt": '<path d="M13 2.5L4.5 13.5h6.5l-1 8 8.5-11h-6.5z"/>',
    "bot": '<rect x="4" y="7.5" width="16" height="12" rx="3"/><path d="M12 3.5v4M9 12.5v2M15 12.5v2M1.5 13v3M22.5 13v3"/><circle cx="12" cy="3" r="1"/>',
    "dollar": '<path d="M12 2.5v19M16.5 6.5c-.8-1.3-2.4-2-4.5-2-2.8 0-4.5 1.4-4.5 3.4 0 4.8 9.5 2.6 9.5 7.6 0 2.1-1.9 3.5-5 3.5-2.4 0-4.2-.9-5-2.4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c.7-4 4-6.5 8-6.5s7.3 2.5 8 6.5"/>',
    "users": '<circle cx="9" cy="8.5" r="3.5"/><path d="M2.5 20c.6-3.4 3.3-5.5 6.5-5.5s5.9 2.1 6.5 5.5"/><path d="M15.5 5.2a3.5 3.5 0 0 1 0 6.6M17.5 14.8c2.1.6 3.6 2.4 4 5.2"/>',
    "check": '<path d="M4.5 12.5l5 5 10-11"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.5l3.5 2"/>',
    "chart": '<path d="M3.5 3.5v17h17"/><path d="M7 15l4-4.5 3 3 5.5-6.5"/>',
    "doc": '<path d="M6 2.5h8l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-17a1 1 0 0 1 1-1z"/><path d="M14 2.5v5h5M8.5 12.5h7M8.5 16h7"/>',
    "code": '<path d="M8.5 7L3.5 12l5 5M15.5 7l5 5-5 5M13.5 4.5l-3 15"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5l5 5"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4.3l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2"/><path d="M14 10a4.5 4.5 0 0 0-6.4-.3l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/>',
    "phone": '<rect x="6.5" y="2" width="11" height="20" rx="2.5"/><path d="M10.5 18.5h3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8 6.6 19.7l1.1-6.1L3.2 9.4l6.1-.8z"/>',
    "lock": '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "spark": '<path d="M12 2.5l1.8 5.7 5.7 1.8-5.7 1.8L12 17.5l-1.8-5.7L4.5 10l5.7-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
    "arrow": '<path d="M4 12h15M13.5 6l6 6-6 6"/>',
    "play": '<path d="M7.5 4.5v15l12-7.5z"/>',
    "gear": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1M18.7 18.7l-2.1-2.1M7.4 7.4L5.3 5.3"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/>',
    "sheet": '<rect x="3.5" y="3.5" width="17" height="17" rx="1.5"/><path d="M3.5 9h17M3.5 14.5h17M9.5 3.5v17"/>',
    "rocket": '<path d="M12 2.5c3.6 2.2 5.5 6 5.5 10.5l-2.5 3h-6l-2.5-3c0-4.5 1.9-8.3 5.5-10.5z"/><circle cx="12" cy="9.5" r="1.8"/><path d="M9 16v2.5M15 16v2.5M12 16v5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "flame": '<path d="M12 2.5c.5 3.5 5.5 5.6 5.5 11a5.5 5.5 0 0 1-11 0c0-2.6 1.3-4.3 2.6-5.6.3 1.9 1.2 3 2.4 3.3-.6-3 .1-6.3.5-8.7z"/>',
    "inbox": '<path d="M3 13.5l2.5-8.5h13L21 13.5v5.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19z"/><path d="M3 13.5h5l1.5 2.5h5l1.5-2.5h5"/>',
    "send": '<path d="M21 3L10.5 13.5M21 3l-6.5 18-4-7.5-7.5-4z"/>',
    "eye": '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "heart": '<path d="M12 20.5s-8.5-5-8.5-11A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8.5 2.5c0 6-8.5 11-8.5 11z"/>',
    "trend_up": '<path d="M3 17.5l6-6 4 4 8-8.5"/><path d="M15 7h6v6"/>',
    "trend_down": '<path d="M3 6.5l6 6 4-4 8 8.5"/><path d="M15 17h6v-6"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5M3 16.5l9 5 9-5"/>',
    "wand": '<path d="M4 20L15.5 8.5M13.5 6.5l2 2"/><path d="M18 2.5v3M16.5 4h3M20.5 9v2M19.5 10h2M9 2.5v2M8 3.5h2"/>',
    "cursor": '<path d="M5 3l14 7.5-6 1.5-2.5 6z"/>',
    "plug": '<path d="M9 2.5v5M15 2.5v5M6.5 7.5h11v4a5.5 5.5 0 0 1-11 0zM12 17v4.5"/>',
    "workflow": '<rect x="2.5" y="3.5" width="7" height="5" rx="1.2"/><rect x="14.5" y="3.5" width="7" height="5" rx="1.2"/><rect x="8.5" y="15.5" width="7" height="5" rx="1.2"/><path d="M6 8.5v3.5h12V8.5M12 12v3.5"/>',
    "megaphone": '<path d="M3.5 10v4a1.5 1.5 0 0 0 1.5 1.5h2l9 4.5V4L7 8.5H5A1.5 1.5 0 0 0 3.5 10z"/><path d="M7 15.5l1.5 5h2.5l-1-4.5M19.5 9.5a3.5 3.5 0 0 1 0 5"/>',
    "question": '<circle cx="12" cy="12" r="9"/><path d="M9.3 9.2a2.8 2.8 0 1 1 3.9 2.6c-.8.4-1.2 1-1.2 1.9v.5"/><circle cx="12" cy="17" r=".8"/>',
    "alert": '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.3" r=".8"/>',
    "home": '<path d="M3.5 11L12 4l8.5 7M6 9.5V20h12V9.5"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8.5 7V5a1.5 1.5 0 0 1 1.5-1.5h4A1.5 1.5 0 0 1 15.5 5v2M3 12.5h18"/>',
    "brain": '<path d="M9 4.5a3 3 0 0 0-3 3 3 3 0 0 0-2 5.2 3.2 3.2 0 0 0 2.5 5.3A3 3 0 0 0 12 19.5V5.5a2.5 2.5 0 0 0-3-1z"/><path d="M15 4.5a3 3 0 0 1 3 3 3 3 0 0 1 2 5.2 3.2 3.2 0 0 1-2.5 5.3A3 3 0 0 1 12 19.5"/>',
}

ICON_NAMES = frozenset(_PATHS)


def icon_svg(name, stroke=2.0, fill="none"):
    if name not in _PATHS:
        raise ValueError(f"unknown icon {name!r}; choose from {', '.join(sorted(_PATHS))}")
    return (f'<svg viewBox="0 0 24 24" fill="{fill}" stroke="currentColor" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_PATHS[name]}</svg>')
