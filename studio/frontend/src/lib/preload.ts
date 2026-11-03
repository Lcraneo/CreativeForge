/** 帧序列预载门控：全部帧进入内存缓存并 decode 后才允许播放/展示，
 * 消除"首过尖峰"（windup 实测其行走预览首过 maxΔ 466ms，二次通过 10ms）。 */

export function preloadImage(
  url: string,
  priority: "high" | "low" = "low",
): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new window.Image();
    image.decoding = "async";
    image.setAttribute("fetchpriority", priority);
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`image load failed: ${url}`));
    image.src = url;
    if (typeof image.decode === "function") void image.decode().catch(() => undefined);
  });
}

/** 并行预载一组图；`preferredIndex` 指向的帧 fetchPriority=high（当前动作/首帧优先）。
 * 返回全部就绪的 Image 元素数组；个别失败不拖垮整体（reject 的槽位为 undefined）。 */
export async function preloadImages(
  urls: readonly string[],
  preferredIndex = 0,
): Promise<(HTMLImageElement | undefined)[]> {
  const unique = [...new Set(urls)];
  return Promise.all(
    unique.map((url, index) =>
      preloadImage(url, index === preferredIndex ? "high" : "low").catch(() => undefined),
    ),
  );
}
