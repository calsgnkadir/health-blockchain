# DOM XSS self-audit of the web UI

A short record of pointing the same source → sink methodology I use on third-party
targets at *this* project's own frontend, what it found, and how it is now
prevented from regressing.

## Why the frontend carries the whole XSS burden

The backend never renders clinical text. It stores it as AES-256-GCM ciphertext and
returns it to the browser verbatim (`tests/test_storage_and_metadata_safety.py`
pins this: escaping is explicitly *not* a storage concern). So every value a user
or a clinician can influence — record titles, notes, doctor/institution names,
usernames, the search box, even server error strings — becomes dangerous only at
the moment the browser turns it into DOM. That moment is an `innerHTML` assignment.
The single defensive control is therefore **contextual output encoding**:
`escapeHtml()` (`backend/static/js/modules/utils.js`) on every interpolation that
reaches an `innerHTML` sink.

## Method

For each `.js` file under `backend/static/js/`:

1. Enumerate the **sinks** — `element.innerHTML = \`…\``, `+=`, template returns
   that are later assigned to `innerHTML`.
2. For each `${…}` interpolation inside a sink, trace the **source** — is the value
   attacker-influenced (came from a form field, an API response echoing input, an
   `Error.message`) or is it a constant?
3. A tainted source reaching a sink **without** `escapeHtml()` is a finding.

Most of the UI already encoded correctly (record modal, user list, audit ledger,
notifications). The audit was about the gaps that did not.

## Findings

### 1. Reflected DOM XSS in the command palette (real, fixed)

`renderCommandPaletteResults()` in `app.js` built the empty-state string from the
raw search box value:

```js
// before
resultsContainer.innerHTML =
  `<div …>No results found for "${query}"</div>`;
```

`query` is `searchInput.value` with only `.trim().toLowerCase()` applied — neither
neutralises HTML. Typing `<img src=x onerror=…>` matches no command or record, so
execution falls to this branch and the payload is parsed as HTML and runs.

- **Impact:** the httpOnly `access_token` cookie keeps the session token out of
  `document.cookie`, so it cannot be stolen by the classic `document.cookie`
  exfiltration. But the script still executes in the victim's authenticated
  origin: it can read the CSRF token the app itself reads and drive any API the
  victim is allowed to (view/download records, grant consent). httpOnly narrows
  the blast radius; it does not make XSS harmless.
- **Fix:** `${escapeHtml(query)}`. Every other interpolation in the same function
  was already encoded — this was the one that was missed.

### 2. Error strings written raw into `innerHTML` (defense-in-depth, fixed)

Eight `catch` handlers across `app.js`, `blockchain.js`, `consent.js` and
`records.js` did `container.innerHTML = \`…${e.message}…\``. An `Error.message`
that echoes attacker input (e.g. a server 4xx whose body reflects a submitted
field) would be reflected into the DOM. Lower likelihood than #1, but the same
class, and inconsistent with the rest of the file. All now go through
`escapeHtml()`.

## Regression guard

`tests/test_frontend_xss.py` is a static (no browser, no server) CI check that:

- fails if a bare `${query}`, `${e.message}` or `${err.message}` ever reappears in
  the shipped JS (i.e. an interpolation that skips `escapeHtml()`);
- asserts the specific command-palette branch stays encoded;
- asserts `escapeHtml()` still encodes all five HTML-significant characters
  (`& < > " '`).

If someone later "simplifies" a sink back to a raw interpolation, the build breaks.

## Cross-check with a static analyzer (and its blind spot)

I also ran my own heuristic source→sink analyzer (`dxa.py`, from a separate
appsec project) over `backend/static/js/`. On the fixed tree it reports **0
high-confidence findings** — no path where one of its recognised *sources*
(`location.*`, `document.referrer`, `postMessage` data, web storage, URL params)
reaches an `innerHTML`/`src` sink unescaped. It still enumerates the ~80
`innerHTML` sink *sites* at medium/low confidence (that is the attack surface, not
a bug), two of which are false positives in the minified `vendor/chart.umd.min.js`.

Worth being explicit: the analyzer would **not** have caught the search-box
finding on its own. Its taint seeds are URL/storage/message sources; it does not
treat a DOM input's `.value` as a source, because same-page input reflection is a
weaker (often self-XSS) class. The command-palette bug was exactly in that blind
spot, and the **manual** source→sink pass is what found it. A heuristic tool is a
net over the common cases, not a proof of absence — which is why the regression
guard above pins the specific sinks rather than trusting a scan to stay clean.

## Note on scope

This is output encoding at the sink, which is the correct primary control for
reflected/stored XSS. It is layered under, not instead of, the app's Content
Security Policy and security headers (`backend/middleware/xss_protection.py`): CSP
is the backstop, contextual encoding is the fix.
