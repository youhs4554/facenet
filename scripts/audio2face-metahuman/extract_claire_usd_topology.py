#!/usr/bin/env python3
"""Run inside UE's PythonScript commandlet to export Claire USD topology."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import unreal
except ModuleNotFoundError:
    unreal = None
if unreal is not None:
    usd_python = (
        Path(unreal.Paths.engine_dir())
        / "Plugins/Runtime/USDCore/Content/Python/Lib/Linux/site-packages"
    )
    sys.path.insert(0, str(usd_python))

from pxr import Usd, UsdGeom


def main() -> None:
    input_path = Path(os.environ["A2F_CLAIRE_TEMPLATE_USD"]).resolve()
    output_path = Path(os.environ["A2F_CLAIRE_TOPOLOGY_JSON"]).resolve()
    stage = Usd.Stage.Open(str(input_path))
    if stage is None:
        raise RuntimeError(f"could not open USD: {input_path}")
    meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get() or []
        counts = mesh.GetFaceVertexCountsAttr().Get() or []
        indices = mesh.GetFaceVertexIndicesAttr().Get() or []
        meshes.append(
            {
                "path": str(prim.GetPath()),
                "point_count": len(points),
                "face_vertex_counts": list(counts),
                "face_vertex_indices": list(indices),
            }
        )
    skin_candidates = [mesh for mesh in meshes if mesh["point_count"] == 1500]
    tongue_candidates = [mesh for mesh in meshes if mesh["point_count"] == 520]
    if len(skin_candidates) != 1 or len(tongue_candidates) != 1:
        raise RuntimeError(
            "expected one 1500-vertex skin and one 520-vertex tongue; "
            f"all meshes={[(item['path'], item['point_count']) for item in meshes]}"
        )
    payload = {
        "schema_version": 1,
        "source_usd": str(input_path),
        "source_license": "NVIDIA Claire sample dataset - evaluation only",
        "skin_mesh": skin_candidates[0],
        "tongue_mesh": tongue_candidates[0],
        "all_meshes": [
            {"path": item["path"], "point_count": item["point_count"]}
            for item in meshes
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"A2F_CLAIRE_TOPOLOGY_EXPORTED={output_path}")


main()
