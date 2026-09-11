# Newspaper Reading

The newspaper header has one navigation row: the paper, the short edition, a sections menu, search, and themes. Publication date stays beside the masthead. Source health, edition history, and permanent links live in the footer.

There are no per-story save, delete/archive, mark-read, or reorder controls. Editorial scores and duplicate sector-filter rows are no longer displayed. The published edition is always complete: old browser saved/read/archive/hidden-publisher state is ignored, not deleted. Legacy saved, archived, catch-up, and preferences routes fall back to the paper. Theme preferences continue to work independently.

Reports retain dedicated pages, publisher attribution, source links, photographs, summaries, and podcast notes where present. Sports keeps its photo-led spreads and scores sidebar. Search is available on demand; sections are native disclosure links and remain usable without JavaScript.

The header regression test checks that the first main headline begins within 300 pixels on desktop and 250 pixels on mobile. Static tests also verify that legacy archived/hidden-publisher data cannot hide published stories.
