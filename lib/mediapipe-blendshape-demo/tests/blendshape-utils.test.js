import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeBlendshapes,
  smoothBlendshapes,
} from "../blendshape-utils.js";

test("normalizeBlendshapes removes neutral, clamps scores, and sorts descending", () => {
  const categories = [
    { categoryName: "mouthSmileLeft", score: 0.72 },
    { categoryName: "_neutral", score: 0.91 },
    { categoryName: "jawOpen", score: 1.2 },
    { categoryName: "eyeBlinkLeft", score: -0.1 },
  ];

  assert.deepEqual(normalizeBlendshapes(categories), [
    { name: "jawOpen", score: 1 },
    { name: "mouthSmileLeft", score: 0.72 },
    { name: "eyeBlinkLeft", score: 0 },
  ]);
});

test("normalizeBlendshapes ignores malformed categories", () => {
  assert.deepEqual(
    normalizeBlendshapes([
      null,
      { categoryName: "", score: 0.4 },
      { categoryName: "jawOpen", score: Number.NaN },
      { categoryName: "mouthPucker", score: 0.3 },
    ]),
    [{ name: "mouthPucker", score: 0.3 }],
  );
  assert.deepEqual(normalizeBlendshapes(), []);
});

test("smoothBlendshapes interpolates previous values without changing order", () => {
  const current = [
    { name: "jawOpen", score: 1 },
    { name: "mouthSmileLeft", score: 0.4 },
  ];
  const previous = new Map([
    ["jawOpen", 0.2],
    ["mouthSmileLeft", 0.6],
  ]);

  assert.deepEqual(smoothBlendshapes(current, previous, 0.25), [
    { name: "jawOpen", score: 0.4 },
    { name: "mouthSmileLeft", score: 0.55 },
  ]);
});

test("smoothBlendshapes uses current values for unseen names and bounds alpha", () => {
  const values = [{ name: "browInnerUp", score: 0.8 }];

  assert.deepEqual(smoothBlendshapes(values, new Map(), 0.3), values);
  assert.deepEqual(
    smoothBlendshapes(values, new Map([["browInnerUp", 0.1]]), 5),
    values,
  );
});
