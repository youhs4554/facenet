export function normalizeBlendshapes(categories = []) {
  if (!Array.isArray(categories)) {
    return [];
  }

  return categories
    .filter(
      (category) =>
        category &&
        category.categoryName &&
        category.categoryName !== "_neutral" &&
        Number.isFinite(Number(category.score)),
    )
    .map((category) => ({
      name: category.categoryName,
      score: Math.max(0, Math.min(1, Number(category.score))),
    }))
    .sort((left, right) => right.score - left.score);
}

export function smoothBlendshapes(current, previous = new Map(), alpha = 0.35) {
  const blend = Math.max(0, Math.min(1, Number(alpha)));
  return current.map(({ name, score }) => {
    if (!previous.has(name)) {
      return { name, score };
    }
    const oldScore = previous.get(name);
    return {
      name,
      score: oldScore + (score - oldScore) * blend,
    };
  });
}
