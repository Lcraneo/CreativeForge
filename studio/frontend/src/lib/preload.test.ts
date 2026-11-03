import { beforeEach, describe, expect, it, vi } from "vitest";

import { preloadImage, preloadImages } from "./preload";

class FakeImage {
  static instances: FakeImage[] = [];
  decoding = "";
  src = "";
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  decode = vi.fn(async () => undefined);
  setAttribute = vi.fn();

  constructor() {
    FakeImage.instances.push(this);
  }
}

vi.stubGlobal("Image", FakeImage);

beforeEach(() => {
  FakeImage.instances = [];
});

describe("preloadImage", () => {
  it("加载成功返回 Image 元素并触发 decode", async () => {
    const pending = preloadImage("a.png", "high");
    const instance = FakeImage.instances[0];
    expect(instance.src).toBe("a.png");
    expect(instance.setAttribute).toHaveBeenCalledWith("fetchpriority", "high");
    instance.onload?.();
    const image = await pending;
    expect(image).toBe(instance);
    expect(instance.decode).toHaveBeenCalled();
  });

  it("加载失败 reject", async () => {
    const pending = preloadImage("broken.png");
    FakeImage.instances[0].onerror?.();
    await expect(pending).rejects.toThrow("broken.png");
  });
});

describe("preloadImages", () => {
  it("全部就绪后 resolve，首选帧 fetchPriority=high", async () => {
    const pending = preloadImages(["a.png", "b.png", "c.png"], 1);
    for (const instance of FakeImage.instances) instance.onload?.();
    const images = await pending;
    expect(images).toHaveLength(3);
    expect(FakeImage.instances[0].setAttribute).toHaveBeenCalledWith("fetchpriority", "low");
    expect(FakeImage.instances[1].setAttribute).toHaveBeenCalledWith("fetchpriority", "high");
    expect(FakeImage.instances[2].setAttribute).toHaveBeenCalledWith("fetchpriority", "low");
  });

  it("url 去重，个别失败不拖垮整体", async () => {
    const pending = preloadImages(["a.png", "a.png", "fail.png"]);
    FakeImage.instances[0].onload?.();
    FakeImage.instances[1].onerror?.();
    const images = await pending;
    expect(FakeImage.instances).toHaveLength(2);
    expect(images[0]).toBeDefined();
    expect(images[1]).toBeUndefined();
  });
});
