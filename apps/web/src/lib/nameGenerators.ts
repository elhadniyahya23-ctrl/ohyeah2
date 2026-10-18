import type { CSSProperties } from "react";

export interface NameGeneratorButton {
  type: string;
  label: string;
  outline?: boolean;
  style?: CSSProperties;
}

export const NAME_GENERATORS: NameGeneratorButton[] = [
  { type: "2C", label: "2C", outline: true },
  { type: "2L", label: "2L", outline: true },
  { type: "2N", label: "2N", outline: true },
  { type: "3C", label: "3C", outline: true },
  { type: "3L", label: "3L", outline: true },
  { type: "3N", label: "3N", outline: true },
  { type: "4N", label: "4N", outline: true },
  { type: "4L", label: "4L", outline: true },
  { type: "4C", label: "4C", outline: true },
  { type: "COMBO2", label: "All 2-Char", outline: true },
  { type: "COMBO3", label: "All 3-Char", outline: true },
  { type: "SEMI3L", label: "Semi 3L (a_bc)", outline: true },
  { type: "SEMI3L_DOT_500", label: "Semi 3L (.abc)", outline: true },
  {
    type: "DOTTED_WORDS_7L",
    label: "Dotted Words (s.e.a)",
    style: { background: "#06b6d4", color: "white", border: "none", boxShadow: "0 2px 8px rgba(6, 182, 212, 0.4)" },
  },
  { type: "EXCEPT4L", label: "All except 4L", outline: true },
  {
    type: "TOP10K",
    label: "TOP 10K Words",
    style: { background: "var(--rbx-accent)", color: "white", border: "none", boxShadow: "0 2px 8px var(--rbx-accent-glow)" },
  },
  {
    type: "TOP20K",
    label: "TOP 20K Words",
    style: { background: "var(--rbx-accent)", color: "white", border: "none", boxShadow: "0 2px 8px var(--rbx-accent-glow)" },
  },
  {
    type: "TOP30K",
    label: "TOP 30K Words",
    style: { background: "var(--rbx-accent)", color: "white", border: "none", boxShadow: "0 2px 8px var(--rbx-accent-glow)" },
  },
  {
    type: "TOP100K",
    label: "TOP 100K Words",
    style: { background: "var(--rbx-accent)", color: "white", border: "none", boxShadow: "0 2px 8px var(--rbx-accent-glow)" },
  },
  {
    type: "TOP10K_FR",
    label: "TOP 10K FR Words",
    style: { background: "#1d4ed8", color: "white", border: "none", boxShadow: "0 2px 8px rgba(29, 78, 216, 0.4)" },
  },
  {
    type: "TOP30K_FR",
    label: "TOP 30K FR Words",
    style: { background: "#1d4ed8", color: "white", border: "none", boxShadow: "0 2px 8px rgba(29, 78, 216, 0.4)" },
  },
  {
    type: "TOP10K_EN_5L",
    label: "TOP 10K EN (5L+)",
    style: { background: "#8b5cf6", color: "white", border: "none", boxShadow: "0 2px 8px rgba(139, 92, 246, 0.4)" },
  },
  {
    type: "TOP10K_FR_5L",
    label: "TOP 10K FR (5L+)",
    style: { background: "#8b5cf6", color: "white", border: "none", boxShadow: "0 2px 8px rgba(139, 92, 246, 0.4)" },
  },
  {
    type: "4L_PRONOUNCE",
    label: "4L Pronounceable",
    style: { background: "#10b981", color: "white", border: "none", boxShadow: "0 2px 8px rgba(16, 185, 129, 0.4)" },
  },
  {
    type: "UNDERSCORE_RPT",
    label: "_ Repeaters",
    style: { background: "#f97316", color: "white", border: "none", boxShadow: "0 2px 8px rgba(249, 115, 22, 0.4)" },
  },
  {
    type: "LETTER_RPT",
    label: "Letter Repeaters",
    style: { background: "#f97316", color: "white", border: "none", boxShadow: "0 2px 8px rgba(249, 115, 22, 0.4)" },
  },
  {
    type: "4L_REPEATERS",
    label: "4L Repeaters 10K",
    style: { background: "#f97316", color: "white", border: "none", boxShadow: "0 2px 8px rgba(249, 115, 22, 0.4)" },
  },
  {
    type: "5L_PRONOUNCE",
    label: "5L Pronounceable 30K",
    style: { background: "#10b981", color: "white", border: "none", boxShadow: "0 2px 8px rgba(16, 185, 129, 0.4)" },
  },
  {
    type: "FACES",
    label: "Faces (X_X / X.X)",
    style: { background: "#ec4899", color: "white", border: "none", boxShadow: "0 2px 8px rgba(236, 72, 153, 0.4)" },
  },
  {
    type: "CITIES_FR",
    label: "Cities (1500)",
    style: { background: "#9333ea", color: "white", border: "none", boxShadow: "0 2px 8px rgba(147, 51, 234, 0.4)" },
  },
  {
    type: "EGIRL_500",
    label: "E-Girl Names (500)",
    style: { background: "#f472b6", color: "white", border: "none", boxShadow: "0 2px 8px rgba(244, 114, 182, 0.4)" },
  },
  {
    type: "EBOY_500",
    label: "E-Boy Names (500)",
    style: { background: "#a855f7", color: "white", border: "none", boxShadow: "0 2px 8px rgba(168, 85, 247, 0.4)" },
  },
  {
    type: "4C_LEET",
    label: "4C Leet Meaning",
    style: { background: "#eab308", color: "white", border: "none", boxShadow: "0 2px 8px rgba(234, 179, 8, 0.4)" },
  },
];
