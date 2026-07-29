/**
 * Applies the persisted theme before first paint, preventing a flash of the
 * wrong palette on reload.
 *
 * Reads the same localStorage key that `src/stores/theme.ts` writes, so the two
 * must agree on the key name and on the Zustand `persist` envelope shape
 * (`{ state: { theme } , version }`).
 */
;(function () {
  var STORAGE_KEY = 'hayabusa.theme'
  var theme = 'dark'

  try {
    var raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      var saved = JSON.parse(raw)
      if (saved && saved.state && (saved.state.theme === 'light' || saved.state.theme === 'dark')) {
        theme = saved.state.theme
      }
    }
  } catch (error) {
    /* Private browsing can throw on localStorage access; the dark default is fine. */
  }

  document.documentElement.setAttribute('data-theme', theme)
})()
