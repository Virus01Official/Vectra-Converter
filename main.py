#!/usr/bin/env python3
"""
osu!mania -> Vectra map.lua converter

Reads an osu! .osu file (mania ruleset) and writes a Lua map file compatible
with the Vectra game format found in `Vectra/maps/*/map.lua`.

Basic mapping rules implemented:
- osu mania columns mapped to x positions used in Vectra maps (4-key layout by default)
- Hit objects (notes) become entries in map:getNotes() with format:
  {type, x, speed, slider_length, time}
  where `type` is 1 for normal notes.

Usage: python tools/osu_to_vectra.py input.osu output_folder [--keys 4]

This is a minimal, dependency-free script. It expects standard osu mania .osu files.
"""

import sys
import os
import argparse
import re
from typing import List, Tuple


def parse_osu_hitobjects(osu_text: str) -> Tuple[List[dict], dict]:
    """Parse [HitObjects] section and return list of notes and metadata dict.

    Returns:
      notes: list of {'x': int, 'time': int, 'type': int, 'end_time': int or None}
      meta: dict with parsed General/Metadata/TimingPoints sections if available
    """
    lines = osu_text.splitlines()
    section = None
    hitobjects = []
    meta = {'timing_points': []}
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith('//'):
            continue
        if ln.startswith('[') and ln.endswith(']'):
            section = ln[1:-1]
            continue
        if section == 'HitObjects':
            # format: x,y,time,type,hitSound,objectParams,extras
            parts = ln.split(',')
            if len(parts) < 5:
                continue
            x = int(parts[0])
            time = int(parts[2])
            type_val = int(parts[3])
            end_time = None
            # for hold notes (mania), objectParams contains end time after ':'
            if type_val & 128:  # osu mania hold note (slider/spinner flags vary)
                # objectParams example for hold: "endTime:..." or "endTime:...|..."
                if len(parts) >= 6:
                    obj = parts[5]
                    m = re.match(r"(\d+):", obj)
                    if m:
                        try:
                            end_time = int(m.group(1))
                        except ValueError:
                            end_time = None
            hitobjects.append({
                'x': x,
                'time': time,
                'type': type_val,
                'end_time': end_time
            })
        elif section == 'TimingPoints':
            # store raw timing point lines for BPM extraction if needed
            meta['timing_points'].append(ln)
    return hitobjects, meta


def load_osu_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def map_column_x_to_Vectra_x(x: int,
                           keys: int,
                           osu_playfield_width: int = 512) -> int:
    """Map osu x coordinate (0..osu_playfield_width) to Vectra x values.

    Vectra maps appear to use x values across a range (e.g., 0..512 or other). We'll
    map columns evenly into the osu playfield width and output the center x.
    """
    # compute column width
    col_width = osu_playfield_width / keys
    # find column index from osu x
    col = int(x / col_width)
    if col < 0:
        col = 0
    if col >= keys:
        col = keys - 1
    # map to Vectra x coordinate: use center of column in 0..512 range
    Vectra_x = int(col * (osu_playfield_width / keys) +
                 (osu_playfield_width / keys) / 2)
    return Vectra_x


def generate_map_lua(title: str,
                     song: str,
                     notes: List[dict],
                     keys: int = 4) -> str:
    """Generate content for a map.lua file.

    Simple mapping: all notes are type=1, speed set to 400, slider_length 0.
    spawn milliseconds equal to note time.
    """
    header = []
    header.append('map = { }')
    header.append('')
    header.append('function map:getBackground()')
    header.append('  return "maps/{}/bg.jpg"'.format(title))
    header.append('end')
    header.append('')
    header.append('function map:getTitle()')
    header.append('  return "{}"'.format(title))
    header.append('end')
    header.append('')
    header.append('function map:getDifficult()')
    header.append('  return "Converted"')
    header.append('end')
    header.append('')
    header.append('function map:getPorter()')
    header.append('  return "osu-converter"')
    header.append('end')
    header.append('')
    header.append('function map:getSong()')
    header.append('  return "{}"'.format(song.replace('\\', '/')))
    header.append('end')
    header.append('')
    # length in seconds (approx max time / 1000)
    max_time = max((n['end_time'] or n['time']) for n in notes) if notes else 0
    header.append('function map:getLength()')
    header.append('  return {}'.format(int((max_time // 1000) + 1)))
    header.append('end')
    header.append('')
    header.append('function map:getNotes()')
    header.append(
        '  -- (0 = none, 1 = normal, 2 = reverse, 3 = bad), (448 = up, 64 = down, 192 = left, 320 = right), speed, slider length, milliseconds to spawn'
    )
    header.append('  return {')

    lines = []
    for n in notes:
        # map osu x to Vectra x using default 512 playfield
        ex = map_column_x_to_Vectra_x(n['x'], keys)
        t = 1  # normal note
        speed = 400
        slider_len = 0
        time_ms = n['time']
        lines.append('    {{{}, {}, {}, {}, {}}},'.format(
            t, ex, speed, slider_len, time_ms))

    header.extend(lines)
    header.append('  }')
    header.append('end')
    header.append('')
    header.append('return map')

    return '\n'.join(header)


def main(argv):
    parser = argparse.ArgumentParser(
        prog='osu_to_Vectra.py',
        description='Convert osu!mania .osu to Vectra map.lua')
    parser.add_argument('input', nargs='?', help='path to .osu file')
    parser.add_argument(
        'output_dir',
        nargs='?',
        help='output folder for map.lua and song reference (not copying song)')
    parser.add_argument(
        '--keys',
        type=int,
        default=4,
        help='number of keys/columns in osu chart (default: 4)')
    args = parser.parse_args(argv)

    # If positional args are missing, prompt interactively
    if not args.input:
        args.input = input('Enter path to .osu file: ').strip()
    if not args.output_dir:
        args.output_dir = input('Enter output folder path: ').strip()

    if not os.path.isfile(args.input):
        print('Input file not found:', args.input)
        sys.exit(2)

    osu_text = load_osu_file(args.input)
    hitobjects, meta = parse_osu_hitobjects(osu_text)

    # naive title extraction from file name
    title = os.path.splitext(os.path.basename(args.input))[0]
    song_path = 'maps/{}/song.mp3'.format(title)

    # filter only mania column notes (x coordinates), convert order
    notes = sorted(hitobjects, key=lambda x: x['time'])

    lua_text = generate_map_lua(title, song_path, notes, keys=args.keys)

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, 'map.lua')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(lua_text)

    print('Wrote', out_path)


if __name__ == '__main__':
    main(sys.argv[1:])
