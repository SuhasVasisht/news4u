# Edition Themes

The palette button opens five newspaper previews: Broadsheet (default), Night Press, Nord, Botanical, and Pop Print. The reader's choice is stored locally under `news4u-theme`, shared across reports and tabs, and restored before paint in newly exported HTML. Layout and story content do not change. Arrow keys, Home/End, Escape, outside click, and reduced-motion preferences are supported.

References: [Nord palettes](https://www.nordtheme.com/docs/colors-and-palettes/) for cool neutrals and restrained accents; [Ettore Sottsass / Memphis](https://designmuseum.org/designers/ettore-sottsass) for the playful contrasting colors in Pop Print. Botanical pairs light foliage tones with plum; Night Press uses neutral charcoal rather than a blue-tinted background.

## Design-Only Deployment

```sh
npm run build:static -- --design-only
npm run deploy:static -- --design-only --revise-today
```

Both commands require the edition data to exactly match the last verified published edition. This mode permits an older publication date, but cannot collect, review, refresh images, or write `data/edition.json`. It does not relabel an old edition as today's paper. Normal daily build/deploy freshness checks are unchanged. Older editions retain their original layout; the latest edition, its dated permalink, and their report pages receive the new design.
