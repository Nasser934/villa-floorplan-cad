# plan.json schema and coordinate conventions

`plan.json` is the canonical, deterministic geometry model. Every export is derived from it.

## Units and coordinates

- Use metres for all plan coordinates, dimensions, areas, levels, and heights.
- Use square metres for areas.
- The local origin is the south-west corner of each floor footprint.
- Positive X runs east. Positive Y runs north. Positive Z runs upward.
- Floor geometry is axis-aligned in the current schema. Preserve exact coordinates across exports.
- OpenSCAD converts metres to millimetres only at export time because OpenSCAD commonly models in millimetres.

## Top-level fields

- `schema_version`: `villa-floorplan-cad.plan.v1`.
- `project`: project name, location, north direction, site data, and source metadata.
- `standards`: configurable design thresholds used by the validator.
- `floors`: floor IDs, labels, levels, clear heights, slab thicknesses, and footprints.
- `rooms`: space type, zone, target area, calculated area, geometry, lighting, ventilation, and metadata.
- `walls`: atomic wall segments with start/end coordinates, type, thickness, and height.
- `openings`: combined door and window opening records.
- `doors`: host boundary, width, height, hinge point, swing, and connected rooms.
- `windows`: host boundary, width, sill, head, and served room.
- `furniture`: editable furniture footprints tied to rooms.
- `fixtures`: editable plumbing and service fixtures tied to rooms.
- `dimensions`: internal room dimensions and overall building dimensions.
- `adjacency_relationships`: shared boundary and door-connectivity information.
- `levels_and_heights`: floor, slab, wall, opening, and parapet settings.
- `vertical_elements`: stairs, elevator shaft, and service shaft geometry.
- `parking`: parking bay geometry and access information.
- `external_access`: guest, family, service, and parking access points.

## Room record

Required fields:

- `id`, `floor_id`, `name`, `type`, `zone`.
- `geometry`: `x_m`, `y_m`, `width_m`, `depth_m`.
- `polygon_m`: four ordered corner points.
- `area_m2`: calculated from geometry.
- `target_area_m2`: program target when provided.
- `requires_natural_light` and `mechanical_ventilation`.

Typical zones are `guest`, `family`, `service`, `shared`, `vertical`, and `external`.

## Stable IDs and deterministic output

- IDs are derived from semantic content using stable hashes.
- JSON keys are sorted on write.
- Coordinates are rounded to four decimal places.
- Do not introduce random IDs, timestamps, or non-deterministic ordering.
- Set `SOURCE_DATE_EPOCH` when reproducible build metadata must match a release pipeline.

## Editing rules

- Treat `program.json` as the design input and `plan.json` as generated output.
- Make intentional geometry changes in `program.json`, then regenerate all exports.
- For direct `plan.json` edits, update every affected room, wall, opening, dimension, adjacency, and vertical element before exporting.
- Never resize a decorative render independently from the canonical geometry.
