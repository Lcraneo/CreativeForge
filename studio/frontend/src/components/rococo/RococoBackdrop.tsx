import "./rococo.css";

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
