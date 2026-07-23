from __future__ import annotations

import json
import os
from functools import lru_cache


def all_edge_sets() -> dict[str, list[list[int]]]:
    return {
        "dlib_parts": DLIB_PARTS_EDGES,
        "dlib_mesh": _dlib_mesh_edges(),
        "mp_contours": _mp_edges("contours"),
        "mp_tess": _mp_edges("tessellation"),
    }


def au_mesh_table() -> dict:
    au_to_vertices = _au_to_vertices()
    region_to_triangles = _au_region_triangles()
    triangles = _canonical_face_tessellation()
    if not triangles:
        triangles = triangles_from_tessellation_edges(_mp_edges("tessellation"))
    vertex_aus: dict[int, list[str]] = {}
    for au, vertices in au_to_vertices.items():
        for vertex in vertices:
            vertex_aus.setdefault(int(vertex), []).append(au)
    return {
        "triangles": triangles,
        "auToVertices": au_to_vertices,
        "regionToTriangles": region_to_triangles,
        "regionToVertices": au_to_vertices,
        "vertexAUs": {str(vertex): aus for vertex, aus in vertex_aus.items()},
    }


def overlay_geometry() -> dict:
    return {
        "edges": all_edge_sets(),
        "auMesh": au_mesh_table(),
    }


def triangles_from_tessellation_edges(edges: list[list[int]]) -> list[list[int]]:
    triangles = []
    for index in range(0, len(edges) - 2, 3):
        a = edges[index][0]
        b = edges[index][1]
        c = edges[index + 1][1]
        triangles.append([int(a), int(b), int(c)])
    return triangles


@lru_cache(maxsize=2)
def _mp_edges(kind: str) -> list[list[int]]:
    try:
        from feat.utils.mp_plotting import FaceLandmarksConnections
    except Exception:
        return []
    edge_sets = {
        "contours": (
            FaceLandmarksConnections.FACE_LANDMARKS_FACE_OVAL,
            FaceLandmarksConnections.FACE_LANDMARKS_LIPS,
            FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE,
            FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE,
            FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYEBROW,
            FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYEBROW,
            FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS,
            FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS,
        ),
        "tessellation": (FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,),
    }
    pairs = []
    for edge_set in edge_sets.get(kind, ()):
        for connection in edge_set:
            pairs.append([int(connection.start), int(connection.end)])
    return pairs


@lru_cache(maxsize=1)
def _au_to_vertices() -> dict[str, list[int]]:
    try:
        from feat.utils.region_maps import load_au_region_map

        return {
            au: [int(vertex) for vertex in spec["mp478_vertices"]]
            for au, spec in load_au_region_map().items()
        }
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _canonical_face_tessellation() -> list[list[int]]:
    try:
        from feat.utils.io import get_resource_path

        path = os.path.join(get_resource_path(), "canonical_face_tessellation.json")
        with open(path) as file:
            return [[int(a), int(b), int(c)] for a, b, c in json.load(file)["triangles"]]
    except Exception:
        return []


@lru_cache(maxsize=1)
def _au_region_triangles() -> dict[str, list[list[int]]]:
    try:
        from feat.utils.region_maps import load_au_region_map

        tessellation = _canonical_face_tessellation()
        if not tessellation:
            return {}
        return {
            au: [tessellation[int(triangle)] for triangle in spec["triangles"]]
            for au, spec in load_au_region_map().items()
        }
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _dlib_mesh_edges() -> list[list[int]]:
    try:
        import numpy as np
        from scipy.spatial import Delaunay
    except Exception:
        return DLIB_PARTS_EDGES
    canonical = np.array(
        [
            [0.10, 0.45], [0.10, 0.55], [0.12, 0.65], [0.15, 0.74],
            [0.20, 0.82], [0.27, 0.88], [0.35, 0.93], [0.43, 0.97],
            [0.50, 0.99], [0.57, 0.97], [0.65, 0.93], [0.73, 0.88],
            [0.80, 0.82], [0.85, 0.74], [0.88, 0.65], [0.90, 0.55],
            [0.90, 0.45], [0.18, 0.32], [0.24, 0.27], [0.32, 0.26],
            [0.40, 0.27], [0.46, 0.31], [0.54, 0.31], [0.60, 0.27],
            [0.68, 0.26], [0.76, 0.27], [0.82, 0.32], [0.50, 0.40],
            [0.50, 0.46], [0.50, 0.52], [0.50, 0.59], [0.43, 0.62],
            [0.46, 0.63], [0.50, 0.64], [0.54, 0.63], [0.57, 0.62],
            [0.23, 0.42], [0.28, 0.39], [0.34, 0.39], [0.39, 0.42],
            [0.34, 0.44], [0.28, 0.44], [0.61, 0.42], [0.66, 0.39],
            [0.72, 0.39], [0.77, 0.42], [0.72, 0.44], [0.66, 0.44],
            [0.34, 0.74], [0.40, 0.71], [0.46, 0.70], [0.50, 0.71],
            [0.54, 0.70], [0.60, 0.71], [0.66, 0.74], [0.60, 0.79],
            [0.54, 0.81], [0.50, 0.82], [0.46, 0.81], [0.40, 0.79],
            [0.36, 0.74], [0.46, 0.73], [0.50, 0.74], [0.54, 0.73],
            [0.64, 0.74], [0.54, 0.77], [0.50, 0.78], [0.46, 0.77],
        ]
    )
    edges: set[tuple[int, int]] = set()
    for simplex in Delaunay(canonical).simplices:
        for a, b in ((simplex[0], simplex[1]), (simplex[1], simplex[2]), (simplex[2], simplex[0])):
            if a > b:
                a, b = b, a
            edges.add((int(a), int(b)))
    return [list(edge) for edge in sorted(edges)]


def _build_dlib_68_face_parts() -> list[list[int]]:
    edges: list[list[int]] = []
    edges.extend([i, i + 1] for i in range(0, 16))
    edges.extend([i, i + 1] for i in range(17, 21))
    edges.extend([i, i + 1] for i in range(22, 26))
    edges.extend([i, i + 1] for i in range(27, 30))
    edges.extend([i, i + 1] for i in range(31, 35))
    edges.extend([i, i + 1] for i in range(36, 41))
    edges.append([41, 36])
    edges.extend([i, i + 1] for i in range(42, 47))
    edges.append([47, 42])
    edges.extend([i, i + 1] for i in range(48, 59))
    edges.append([59, 48])
    edges.extend([i, i + 1] for i in range(60, 67))
    edges.append([67, 60])
    return edges


DLIB_PARTS_EDGES = _build_dlib_68_face_parts()
