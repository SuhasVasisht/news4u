"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Check, Palette } from "lucide-react";
import { editionThemes, themeStorageKey, validTheme, type EditionTheme } from "@/lib/edition-themes";

export function ThemePicker() {
  const [theme, setTheme] = useState<EditionTheme>("broadsheet");
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const choices = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    const apply = (value: unknown) => {
      const next = validTheme(value) ? value : "broadsheet";
      document.documentElement.dataset.theme = next;
      setTheme(next);
    };
    try { apply(localStorage.getItem(themeStorageKey)); } catch { /* Storage is optional. */ }
    const sync = (event: StorageEvent) => { if (event.key === themeStorageKey || event.key === null) apply(event.newValue); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  useEffect(() => {
    if (!open) return;
    choices.current[editionThemes.findIndex(item => item.id === theme)]?.focus();
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, theme]);

  function choose(next: EditionTheme) {
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(themeStorageKey, next); } catch { /* Apply for this visit even without storage. */ }
    setOpen(false);
    trigger.current?.focus();
  }

  return <div className="theme-picker" ref={root} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
  }}>
    <button ref={trigger} className="tool" title="Choose theme" aria-label="Choose theme" aria-expanded={open} aria-haspopup="menu" aria-controls="edition-theme-menu" onClick={() => setOpen(value => !value)} onKeyDown={event => {
      if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); }
    }}><Palette /></button>
    {open && <div id="edition-theme-menu" className="theme-menu" role="menu" aria-label="Paper theme">
      {editionThemes.map((item, index) => <button key={item.id} ref={element => { choices.current[index] = element; }} role="menuitemradio" aria-checked={theme === item.id} tabIndex={theme === item.id ? 0 : -1} className="theme-choice" style={{ "--preview-paper": item.paper, "--preview-ink": item.ink, "--preview-accent": item.accent, "--preview-secondary": item.secondary } as CSSProperties} onClick={() => choose(item.id)} onKeyDown={event => {
        const steps: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 2, ArrowUp: -2 };
        let next = index;
        if (event.key in steps) next = (index + steps[event.key] + editionThemes.length) % editionThemes.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = editionThemes.length - 1;
        else return;
        event.preventDefault(); choices.current[next]?.focus();
      }}>
        <span className="theme-preview" aria-hidden="true"><span className="theme-preview-title">Aa.</span><span className="theme-preview-lines"><i /><i /><i /></span><span className="theme-preview-swatch" /></span>
        <span className="theme-choice-label">{item.name}{theme === item.id && <Check />}</span>
      </button>)}
    </div>}
  </div>;
}
