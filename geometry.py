def panel_rect(edge_width, panel_width, margin):
    margin = max(0, int(margin))
    width = max(1, min(int(panel_width), int(edge_width)))
    x = max(0, (int(edge_width) - width) // 2)
    return x, margin, width, 0


def input_region(edge_width, visible_width, height):
    left = max(0, (int(edge_width) - int(visible_width)) // 2)
    return left, 0, max(0, int(visible_width)), max(0, int(height))


SECTIONS = ('all', 'media', 'agenda', 'shelf')


def next_section(current, enabled):
    names = [name for name in SECTIONS if name == 'all' or enabled.get(name, False)]
    if not names:
        return 'all'
    if current not in names:
        return names[0]
    return names[(names.index(current) + 1) % len(names)]
