// Runs before the masthead is painted; the link is visible without this script.
try {
  if (!sessionStorage.getItem('mynews-masthead')) {
    sessionStorage.setItem('mynews-masthead', 'printed');
    document.documentElement.classList.add('masthead-enter');
  }
} catch (_) {
  // Storage can be disabled. Keep the static masthead rather than replaying it.
}
