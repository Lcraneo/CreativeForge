import "./rococo.css";

/**
 * 背景纸面元素（样板图取景）：远山城堡。纯装饰层，不承载任何信息，不拦截指针事件。
 */
export function RococoBackdrop() {
  return (
    <>
      {/* 远山城堡 */}
      <svg
        viewBox="0 0 560 180"
        fill="none"
        aria-hidden="true"
        className="cf-backdrop__castle"
      >
        <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
          {/* 地面与远山 */}
          <path d="M2 168c58-14 96 4 150-2 54-6 92 10 140 4 60-8 112 6 156-2 44-8 78 4 110 0" strokeWidth="1" />
          <path d="M-6 176c80-10 126 2 190-4 76-7 128 9 196 3 56-5 118 5 186-3" strokeWidth="0.7" strokeDasharray="4 5" opacity="0.7" />

          {/* 左塔 */}
          <path d="M112 100h54v70" strokeWidth="1.1" />
          <path d="M112 100h54" strokeWidth="1.1" />
          <path d="M106 100l33-40 33 40" strokeWidth="1.1" />
          <path d="M139 44v-14" strokeWidth="0.9" />
          <path d="M139 30l14 5-14 5" strokeWidth="0.9" />
          <path d="M126 122a8 8 0 0 1 16 0v10" strokeWidth="0.9" />
          <path d="M130 146a4 4 0 0 1 8 0v8" strokeWidth="0.8" />

          {/* 主楼 */}
          <path d="M250 96h104v74" strokeWidth="1.1" />
          <path d="M250 96v-10h12v10M272 86h12v10M296 86h12v10M320 86h12v10M342 86h12v10" strokeWidth="0.9" />
          <path d="M272 96l30-50 30 50" strokeWidth="1.1" />
          <path d="M302 30v-12M302 18l13 4.5-13 4.5" strokeWidth="0.9" />
          <path d="M266 126a10 10 0 0 1 20 0v12" strokeWidth="0.95" />
          <path d="M322 122a10 10 0 0 1 20 0v12" strokeWidth="0.95" />
          <path d="M296 152a6 6 0 0 1 12 0v18" strokeWidth="0.9" />

          {/* 右塔 */}
          <path d="M420 112h48v58" strokeWidth="1.1" />
          <path d="M414 112l30-36 30 36" strokeWidth="1.1" />
          <path d="M444 62v-12M444 50l12 4-12 4" strokeWidth="0.85" />
          <path d="M434 134a7 7 0 0 1 14 0v10" strokeWidth="0.9" />

          {/* 小屋与树 */}
          <path d="M186 134h42v36M186 134l21-16 21 16" strokeWidth="1" />
          <path d="M200 158a6 6 0 0 1 12 0v12" strokeWidth="0.85" />

          <path d="M86 170v-26" strokeWidth="1" />
          <path d="M86 148c-10-2-16-9-13-16 3-6 11-6 14 0 1-8 8-11 13-7 5 4 4 12-2 16-4 3-8 3-12 2" strokeWidth="0.9" />
          <path d="M512 170v-22" strokeWidth="1" />
          <path d="M512 152c-9-1-15-8-12-14 2-6 9-6 12-1 0-7 7-10 11-6 4 4 3 11-2 14-3 2-6 2-9 1" strokeWidth="0.9" />
        </g>
      </svg>

    </>
  );
}

/** 花体首字母水印（侧栏留白处的品牌字迹） */
export function RococoLetterMark() {
  return (
    <span className="cf-backdrop__letter" aria-hidden="true">
      Cf
    </span>
  );
}

/** 手账信笺与旧书（侧栏底部纸面角饰） */
export function RococoJournal() {
  return (
    <svg viewBox="0 0 240 210" fill="none" aria-hidden="true" className="cf-backdrop__journal">
        <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
          {/* 旧书三叠 */}
          <path d="M18 192l150-10 12 9-152 11z" strokeWidth="1" />
          <path d="M26 180l140-9 12 8-142 11z" strokeWidth="1" opacity="0.85" />
          <path d="M36 168l128-8 12 8-132 10z" strokeWidth="0.9" opacity="0.7" />
          <path d="M60 176l4 8M96 173l4 8M132 170l4 8" strokeWidth="0.7" opacity="0.6" />

          {/* 信笺 */}
          <g transform="rotate(-7 108 96)">
            <rect x="46" y="46" width="126" height="98" rx="4" strokeWidth="1.1" />
            <rect x="52" y="52" width="114" height="86" rx="2.5" strokeWidth="0.7" strokeDasharray="3 4" opacity="0.75" />
            <path d="M62 72h66M62 86h80M62 100h56M62 114h72" strokeWidth="0.7" opacity="0.55" />
            <path d="M148 62c8 0 12 4 12 9s-5 8-11 8c-3 0-5-2-5-4" strokeWidth="0.8" opacity="0.7" />
          </g>

          {/* 蜡封与缎带 */}
          <circle cx="158" cy="142" r="12" strokeWidth="1" />
          <circle cx="158" cy="142" r="7" strokeWidth="0.7" strokeDasharray="2 3" opacity="0.8" />
          <path d="M158 137c2.6 1 4.4 3 4.4 5.6 0 3-2 5.4-4.4 5.4s-4.4-2.4-4.4-5.4c0-2.6 1.8-4.6 4.4-5.6z" strokeWidth="0.7" opacity="0.9" />
          <path d="M147 148c-4 6-6 10-5 14 3-2 7-4 10-4M169 148c4 6 6 10 5 14-3-2-7-4-10-4" strokeWidth="0.8" opacity="0.7" />

          {/* 玫瑰小枝 */}
          <path d="M188 40c10-8 22-8 30-2" strokeWidth="0.85" />
          <path d="M198 46c-6-6-6-13 0-16 6 3 8 9 4 15" strokeWidth="0.85" />
          <path d="M214 42c4-5 3-11-1-13-4 2-5 7-2 11" strokeWidth="0.75" opacity="0.85" />
        </g>
    </svg>
  );
}
