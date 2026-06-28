# QA checks and fixes (validate output → you fix index.html accordingly)

`validate.py` checks the `index.html` you wrote and produces `validation.json` + `qa_report.md`.
**Errors must be cleared to zero** to pass; **warnings are fixed case by case** (fix most, a few are acceptable).

## error (structural, must fix)

| Report | Cause | Fix |
|---|---|---|
| `HTML does not start with <!DOCTYPE html>` | Missing doctype declaration | Write `<!DOCTYPE html>` as the first line |
| `HTML is missing </html>` | Incomplete structure | Add the closing `</html>` |
| `Missing image files: images/x` | References a non-existent image | Check the filename (from `manifest.figures[].file`/`tables[].image`); only reference images parse_pdf copied into `images/`; don't mistype the hash name |
| `Found N empty href="#" links` | Empty anchors | Give a real link or remove the `<a>` |

## warning (fix as needed)

| Report | Meaning | Handling |
|---|---|---|
| `Paper title not found in the page` | The first 40 chars of the title don't appear on the page | Make sure the hero uses the real title text from the manifest |
| `None of the extracted figures are referenced` | Not one extracted figure is used | Show at least the main figure (architecture/pipeline) |
| `None of the extracted result tables are referenced` | No result table is used | Put a result-table screenshot in the results section |
| `Repeated image references` | The same image is referenced multiple times | Usually deduplicate; unless intentional (teaser+gallery) |
| `Fewer than three impact claims were extracted` | manifest.claims<3 | Extraction limit, no need to pad; you can naturally write the key numbers from abstract/results into the copy |
| `No paper link was detected` | links.paper empty (no arxiv assumption) | If you know the canonical link, re-run Step 1 with `--paper-url`; otherwise accept it empty |
| `No code link was detected` | links.code empty | If the paper provides a code repo, re-run Step 1 with `--code-url`; otherwise accept it empty |
| `No figures were detected` | manifest.figures empty | Extraction limit (or the paper truly has no figures); fine to leave a text-only page |
| `No table screenshots were detected; results will use extracted HTML tables` | No table has a cropped screenshot | Acceptable; render the result tables as native HTML, or re-run Step 1 if a screenshot is expected |
| `Link(s) not traceable to the paper source (possible fabrication; verify or remove)` | A clickable `<a href="http…">` on the page can't be traced to the paper source or a manifest link — likely a fabricated/hallucinated URL | Remove the link or replace it with a real one from `manifest.links` / the paper; only fabrications are flagged (CDN/font and arxiv/doi domains are allowed) |
| `non-decorative images with empty alt` | An image has `alt=""` | Add the caption as alt; for purely decorative images add `aria-hidden="true"` |

## Loop

Fix `index.html` → re-run `validate.py --workdir <...>` → until errors are zero and warnings acceptable.
QA doesn't edit your HTML, it only reports — you remain the lead author throughout.
