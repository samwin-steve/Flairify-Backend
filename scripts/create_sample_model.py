"""Original CC0 studio mannequin. Geometry only; never a personal avatar."""

import json, math, struct
from pathlib import Path

positions = []
normals = []
indices = []
# Simple ellipsoids build a neutral dress form, limbs and plinth, without facial likeness.
parts = [
    ((0, 1.65, 0), (0.115, 0.15, 0.10)),
    ((0, 1.47, 0), (0.07, 0.07, 0.07)),
    ((0, 1.24, 0), (0.22, 0.25, 0.115)),
    ((0, 1.02, 0), (0.15, 0.15, 0.10)),
    ((0, 0.85, 0), (0.195, 0.18, 0.13)),
    ((-0.12, 0.48, 0), (0.085, 0.37, 0.09)),
    ((0.12, 0.48, 0), (0.085, 0.37, 0.09)),
    ((-0.13, 0.12, 0.045), (0.085, 0.065, 0.15)),
    ((0.13, 0.12, 0.045), (0.085, 0.065, 0.15)),
    ((-0.275, 1.18, 0), (0.065, 0.245, 0.065)),
    ((0.275, 1.18, 0), (0.065, 0.245, 0.065)),
    ((-0.30, 0.89, 0), (0.05, 0.11, 0.055)),
    ((0.30, 0.89, 0), (0.05, 0.11, 0.055)),
    ((0, 0.025, 0), (0.38, 0.025, 0.30)),
]
for center, scale in parts:
    base = len(positions)
    nlat = 18
    nlon = 28
    for a in range(nlat + 1):
        phi = math.pi * a / nlat
        for b in range(nlon + 1):
            theta = 2 * math.pi * b / nlon
            normal = (math.sin(phi) * math.cos(theta), math.cos(phi), math.sin(phi) * math.sin(theta))
            positions.append(tuple(center[k] + scale[k] * normal[k] for k in range(3)))
            adjusted = [normal[k] / scale[k] for k in range(3)]
            length = math.sqrt(sum(x * x for x in adjusted))
            normals.append(tuple(x / length for x in adjusted))
    for a in range(nlat):
        for b in range(nlon):
            i = base + a * (nlon + 1) + b
            j = i + nlon + 1
            indices.extend([i, j, i + 1, i + 1, j, j + 1])
pb = b"".join(struct.pack("<3f", *p) for p in positions)
nb = b"".join(struct.pack("<3f", *p) for p in normals)
ib = struct.pack("<" + "I" * len(indices), *indices)
binary = pb + nb + ib
model = {
    "asset": {"version": "2.0", "generator": "Flairify original CC0 procedural sample"},
    "scene": 0,
    "scenes": [{"nodes": [0]}],
    "nodes": [{"mesh": 0}],
    "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
    "materials": [
        {
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.72, 0.48, 0.53, 1],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.65,
            },
            "doubleSided": True,
        }
    ],
    "buffers": [{"byteLength": len(binary)}],
    "bufferViews": [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(pb), "target": 34962},
        {"buffer": 0, "byteOffset": len(pb), "byteLength": len(nb), "target": 34962},
        {"buffer": 0, "byteOffset": len(pb) + len(nb), "byteLength": len(ib), "target": 34963},
    ],
    "accessors": [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": len(positions),
            "type": "VEC3",
            "min": [min(p[k] for p in positions) for k in range(3)],
            "max": [max(p[k] for p in positions) for k in range(3)],
        },
        {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
        {"bufferView": 2, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
    ],
}
js = json.dumps(model, separators=(",", ":")).encode()
js += b" " * ((-len(js)) % 4)
binary += b"\0" * ((-len(binary)) % 4)
out = (
    struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    + struct.pack("<II", len(js), 0x4E4F534A)
    + js
    + struct.pack("<II", len(binary), 0x004E4942)
    + binary
)
path = Path(__file__).resolve().parents[2] / "frontend/public/models/flairify-form.glb"
path.write_bytes(out)
print("Sample GLB:", len(out), "bytes")
