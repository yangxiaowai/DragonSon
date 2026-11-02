#!/usr/bin/env python3
"""Check packaged file integrity and the documented sprite grid.

This verifies the committed artifact, not animation semantics or Pets acceptance.
The original production checks and visual reviews are archived in validation/.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'manifest.json').read_text())
    errors = []
    for relative, expected in manifest['files'].items():
        path = root / relative
        if not path.is_file():
            errors.append(f'Missing file: {relative}')
            continue
        content = path.read_bytes()
        if len(content) != expected['bytes']:
            errors.append(f'Byte length mismatch: {relative}')
        if hashlib.sha256(content).hexdigest() != expected['sha256']:
            errors.append(f'SHA256 mismatch: {relative}')

    atlas_path = root / manifest['sprite']['path']
    with Image.open(atlas_path) as atlas:
        if atlas.format != 'PNG' or atlas.mode != 'RGBA':
            errors.append('Expected transparent RGBA PNG')
        if atlas.size != (1536, 2288):
            errors.append(f'Wrong atlas dimensions: {atlas.size}')
        else:
            alpha = atlas.getchannel('A')
            for row, count in enumerate(manifest['sprite']['frames_per_row']):
                for column in range(8):
                    cell = alpha.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208))
                    occupied = cell.getbbox() is not None
                    if occupied != (column < count):
                        errors.append(f'Unexpected cell occupancy: row {row}, column {column}')

    result = {'ok': not errors, 'files_checked': len(manifest['files']),
              'required_frames': sum(manifest['sprite']['frames_per_row']),
              'errors': errors,
              'scope': 'Packaged hashes, format, dimensions and occupied cells; not visual acceptance.'}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
