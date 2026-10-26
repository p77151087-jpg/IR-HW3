// Display sorting only. All cells are escaped in Python; never interpret their HTML.
(() => {
    document.querySelectorAll(".rank-overview-scroll").forEach(root => {
        if (root.dataset.sortReady) return;
        root.dataset.sortReady = "true";
        const table = root.querySelector("table");
        const body = table.tBodies[0];
        const rows = Array.from(body.rows);
        const originalIndex = new Map(rows.map((row, index) => [row, index]));
        const headers = Array.from(table.tHead.rows[0].cells);
        const collator = new Intl.Collator("en", {sensitivity: "base", numeric: true});
        headers.forEach((header, column) => {
            header.querySelector("button").addEventListener("click", () => {
                const descending = header.getAttribute("aria-sort") !== "descending";
                const numeric = header.dataset.sortType === "number";
                const sorted = rows.slice().sort((a, b) => {
                    const av = a.cells[column].textContent.trim();
                    const bv = b.cells[column].textContent.trim();
                    const aMissing = av === "—" || av === "";
                    const bMissing = bv === "—" || bv === "";
                    // Missing ranks stay below known ranks in both directions.
                    if (aMissing !== bMissing) return aMissing ? 1 : -1;
                    const delta = aMissing ? 0 : numeric ? Number(av) - Number(bv) : collator.compare(av, bv);
                    return (descending ? -delta : delta) || originalIndex.get(a) - originalIndex.get(b);
                });
                body.append(...sorted);
                headers.forEach(item => item.setAttribute("aria-sort", "none"));
                header.setAttribute("aria-sort", descending ? "descending" : "ascending");
                root.scrollTop = 0;
                const status = root.nextElementSibling;
                status.textContent = `目前依「${header.textContent}」由${descending ? "高到低" : "低到高"}排列；「—」固定排最後。`;
            });
        });
    });
})();
