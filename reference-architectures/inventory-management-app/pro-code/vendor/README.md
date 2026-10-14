# Vendored runtime libraries

The Domo Mobile WebView must be able to finish loading the Pro Code iframe even when an external CDN is unavailable. The two runtime libraries used during application startup are therefore shipped in the Pro Code bundle.

| File | Package | Version | License | Upstream |
|---|---|---:|---|---|
| `domo.js` | `ryuu.js` | 4.6.0 | See `ryuu.js-4.6.0.LICENSE` | `https://www.npmjs.com/package/ryuu.js/v/4.6.0` |
| `jsQR.js` | `jsqr` | 1.4.0 | Apache-2.0; see `jsQR-1.4.0.LICENSE` | `https://www.npmjs.com/package/jsqr/v/1.4.0` |

The files are copied without modification from the corresponding npm package tarballs. Do not replace them with an unpinned CDN URL. When upgrading, update the version, license copy, hashes in the handoff, and mobile loading tests together.
