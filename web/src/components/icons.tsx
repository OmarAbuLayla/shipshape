// A handful of line icons, drawn inline so the app has no icon dependency.

type IconProps = { size?: number };

const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
});

export const Sun = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
);
export const Moon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" /></svg>
);
export const Folder = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
);
export const Upload = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></svg>
);
export const Check = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
);
export const Alert = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M12 3l10 18H2zM12 10v5M12 18v.01" /></svg>
);
export const Book = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7" /></svg>
);
export const Trash = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>
);
export const Close = ({ size = 14 }: IconProps) => (
  <svg {...base(size)}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const Copy = ({ size = 14 }: IconProps) => (
  <svg {...base(size)}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>
);
