import { describe, expect, it } from "vitest";
import {
  backgroundSequenceAt,
  containRect,
  coverBackgroundRect,
  platformMaterialFor,
} from "./sceneVisuals";

const palette = {
  skyTop: "#14213d",
  skyBottom: "#89a7c2",
  ground: "#4f5968",
  floating: "#d8eef7",
  accent: "#7fd8ff",
};

describe("scene visuals", () => {
  it("contains a 16:9 image without cropping or distortion", () => {
    const fit = containRect(1280, 720, 800, 400);
    expect(fit.width).toBeCloseTo(711.111, 2);
    expect(fit.height).toBeCloseTo(400, 5);
    expect(fit.x).toBeCloseTo(44.444, 2);
    expect(fit.y).toBe(0);
    expect(fit.width / fit.height).toBeCloseTo(16 / 9, 5);
  });

  it("covers the viewport with only a small crop for a scrolling backdrop", () => {
    const cover = coverBackgroundRect(1280, 720, 760, 420);
    expect(cover.width).toBe(760);
    expect(cover.height).toBe(420);
    expect(cover.cropWidth).toBeCloseTo(1280, 5);
    expect(cover.cropHeight).toBeCloseTo(707.37, 2);
    expect(cover.cropY).toBeCloseTo(6.32, 2);
  });

  it("maps level progress across the generated background sequence", () => {
    expect(backgroundSequenceAt(0, 5)).toEqual({ from: 0, to: 1, mix: 0 });
    expect(backgroundSequenceAt(0.5, 5)).toEqual({ from: 2, to: 3, mix: 0 });
    expect(backgroundSequenceAt(0.625, 5)).toEqual({ from: 2, to: 3, mix: 0.5 });
    expect(backgroundSequenceAt(1, 5)).toEqual({ from: 4, to: 4, mix: 0 });
    expect(backgroundSequenceAt(0.8, 1)).toEqual({ from: 0, to: 0, mix: 0 });
  });

  it("uses distinct snow and ice materials for ground and floating platforms", () => {
    const ground = platformMaterialFor("ground", palette, "snow", ["ice_theme"]);
    const floating = platformMaterialFor("floating", palette, "snow", ["ice_theme"]);
    expect(ground.flavor).toBe("snow");
    expect(floating.flavor).toBe("ice");
    expect(ground.base).not.toBe(floating.base);
  });

  it("falls back to the palette for invalid theme colors", () => {
    const material = platformMaterialFor("floating", palette, "forest");
    expect(material.flavor).toBe("moss");
    expect(material.base).toBe(palette.floating);
    expect(material.joint).toMatch(/^#[0-9a-f]{6}$/);
  });
});
