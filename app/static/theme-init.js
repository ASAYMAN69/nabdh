// Apply the stored colour scheme before first paint.
// Kept in an external file so the app can run under a strict script-src 'self' CSP.
try {
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.content = localStorage.getItem("color-scheme") ?? "light dark";
  }
} catch {
  /* storage unavailable — fall back to the meta tag default */
}
