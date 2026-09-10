export const editionThemes = [
  { id: "broadsheet", name: "Broadsheet", paper: "#ffffff", ink: "#222222", accent: "#333333", secondary: "#555555" },
  { id: "night", name: "Night Press", paper: "#191b1d", ink: "#eceeec", accent: "#a8d5cf", secondary: "#e5b777" },
  { id: "nord", name: "Nord", paper: "#eceff4", ink: "#2e3440", accent: "#355e78", secondary: "#864b5c" },
  { id: "botanical", name: "Botanical", paper: "#f0f5ed", ink: "#25382b", accent: "#754365", secondary: "#397457" },
  { id: "pop", name: "Pop Print", paper: "#fff1f4", ink: "#34252e", accent: "#aa254a", secondary: "#14686b" },
] as const;
export type EditionTheme = typeof editionThemes[number]["id"];
export const themeStorageKey = "news4u-theme";
export function validTheme(value: unknown): value is EditionTheme {
  return editionThemes.some(theme => theme.id === value);
}
// Runs before first paint on exported pages; a blocked storage API keeps the default.
export const themeBootstrap = `try{var t=localStorage.getItem(${JSON.stringify(themeStorageKey)});if(${JSON.stringify(editionThemes.map(t => t.id))}.includes(t))document.documentElement.dataset.theme=t;}catch{}`;
