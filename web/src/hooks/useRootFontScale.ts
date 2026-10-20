import { useEffect, useState } from 'react';

/**
 * The root font size relative to the 16px default: 2 when a visitor doubles their text
 * size. SVG text is sized in rem, so the chart widens its margins by the same factor.
 */
export function useRootFontScale(): number {
  const [scale, setScale] = useState(readScale);
  useEffect(() => {
    const update = () => setScale(readScale());
    window.addEventListener('resize', update); // page zoom; a text-size change reloads or resizes
    return () => window.removeEventListener('resize', update);
  }, []);
  return scale;
}

function readScale(): number {
  const px = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(px) && px > 0 ? px / 16 : 1;
}
