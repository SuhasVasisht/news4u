import { hydrateRoot } from "react-dom/client";
import { NewsEdition } from "../src/components/edition/news-edition";
import type { EditionData } from "../src/lib/edition";

const root = document.getElementById("edition-root")!;
const edition = JSON.parse(document.getElementById("edition-data")!.textContent!) as EditionData;
hydrateRoot(root, <NewsEdition edition={edition} staticMode archivedEdition={root.dataset.archive === "true"} initialStory={root.dataset.story || null} />);
