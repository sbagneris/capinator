// Delegated "copy to clipboard" handler.
//
// Buttons opt in with either data-copy-target="<element id>" (copies that element's
// value) or data-copy-text="<literal>". Keeping this out of inline onclick= attributes
// is what lets the Content-Security-Policy use script-src 'self' with no 'unsafe-inline'.
// Delegating from document also covers buttons HTMX swaps in after page load.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy-target], [data-copy-text]");
  if (!button) return;

  const { copyTarget, copyText } = button.dataset;
  const text =
    copyText !== undefined
      ? copyText
      : document.getElementById(copyTarget)?.value ?? "";

  navigator.clipboard.writeText(text);
});
