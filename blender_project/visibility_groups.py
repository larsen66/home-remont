"""Organize generated details for independent Outliner visibility controls."""
import bpy

DETAILS_NAME = '3D ДЕТАЛИ - скрыть всё'


def organize_visibility():
    details = bpy.data.collections.new(DETAILS_NAME)
    bpy.context.scene.collection.children.link(details)

    def group(name, parent=details):
        c = bpy.data.collections.new(name)
        parent.children.link(c)
        return c

    windows = group('ОКНА - скрыть оба блока')
    living = group('ОКНО - зал', windows)
    bedroom = group('ОКНО - спальня', windows)
    doors = group('ДВЕРЬ - входная')
    beams = group('БАЛКИ И ПЕРЕМЫЧКИ')
    niches = group('НИШИ - стенки и верхние выступы')
    balcony = group('БАЛКОН - ограждение')

    for obj in list(bpy.data.objects):
        # Only generated objects, never objects from the manual collection.
        if not any(c.name.startswith(('09 ОКНА', '10 ОКНА', '11 БАЛКИ', '12 БАЛКОН', '03 Walls')) for c in obj.users_collection):
            continue
        name = obj.name
        target = None
        if name.startswith('LK balcony /'):
            target = living
        elif name.startswith('BR balcony /'):
            target = bedroom
        elif name.startswith(('LK entrance door /', 'LK entrance handle')):
            target = doors
        elif 'niche' in name.lower():
            target = niches
        elif name.startswith('Balcony /'):
            target = balcony
        elif obj.get('feature_id') or name.startswith('LK entrance lintel'):
            target = beams
        if target:
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            target.objects.link(obj)

    for c in list(bpy.data.collections):
        if c.name.startswith(('09 ОКНА','10 ОКНА','11 БАЛКИ','12 БАЛКОН')) and not c.all_objects:
            bpy.data.collections.remove(c)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'OUTLINER':
                area.spaces.active.show_restrict_column_hide = True
                area.spaces.active.show_restrict_column_render = True
    return details
