import { cx } from "./ui";

/**
 * Deterministic pixel "actor" used to visualise animation frames.
 * The pose (arm/leg swing) is derived from the frame phase so the
 * timeline reads as a real walk/attack cycle.
 */
export function FrameFigure({
  phase = 0,
  active = false,
  className,
}: {
  phase?: number;
  active?: boolean;
  className?: string;
}) {
  const swing = Math.sin(phase * Math.PI * 2);
  const lead = Math.round(swing * 1.4);
  const armLift = Math.round(Math.cos(phase * Math.PI * 2) * 1.2);
  const bounce = Math.abs(swing) > 0.6 ? -1 : 0;

  const outfit = active ? "var(--color-primary)" : "var(--color-ink-3)";
  const skin = "var(--color-paper)";
  const dark = active ? "var(--color-ink)" : "var(--color-ink-4)";

  const cells: Array<[number, number, string, number?]> = [
    // hair / head (top at y0)
    [4, 0, dark], [5, 0, dark], [6, 0, dark], [7, 0, dark],
    [3, 1, dark], [4, 1, dark], [5, 1, dark], [6, 1, dark], [7, 1, dark], [8, 1, dark],
    [3, 2, dark],
    [8, 2, dark],
    // face
    [4, 2, skin], [5, 2, skin], [6, 2, skin], [7, 2, skin],
    [4, 3, skin], [5, 3, dark], [6, 3, skin], [7, 3, dark],
    [5, 4, skin], [6, 4, skin],
    // torso
    [4, 5 + bounce, outfit], [5, 5 + bounce, outfit], [6, 5 + bounce, outfit], [7, 5 + bounce, outfit],
    [4, 6 + bounce, outfit], [5, 6 + bounce, skin], [6, 6 + bounce, skin], [7, 6 + bounce, outfit],
    [4, 7 + bounce, outfit], [5, 7 + bounce, outfit], [6, 7 + bounce, outfit], [7, 7 + bounce, outfit],
    // belt
    [4, 8 + bounce, dark], [5, 8 + bounce, dark], [6, 8 + bounce, dark], [7, 8 + bounce, dark],
    // arms (opposite swing to legs)
    [3, 5 + bounce - armLift, outfit],
    [3, 6 + bounce - armLift, skin],
    [8, 5 + bounce + armLift, outfit],
    [8, 6 + bounce + armLift, skin],
  ];

  // legs — lead leg strides forward, trail leg back
  const legY = 9 + bounce;
  cells.push([5, legY, dark], [6, legY, dark]);
  cells.push([4 + lead, legY + 1, dark], [5 + lead, legY + 1, dark]);
  cells.push([7 - lead, legY + 1, dark], [8 - lead, legY + 1, dark]);
  cells.push([4 + lead, legY + 2, dark]);
  cells.push([8 - lead, legY + 2, dark]);

  return (
    <svg
      viewBox="0 0 12 14"
      shapeRendering="crispEdges"
      role="img"
      aria-label="animation frame"
      className={cx(className, active ? "opacity-100" : "opacity-80")}
    >
      {cells.map(([x, y, fill], index) => (
        <rect key={index} x={x - 2} y={y} width={1} height={1} fill={fill} />
      ))}
    </svg>
  );
}
