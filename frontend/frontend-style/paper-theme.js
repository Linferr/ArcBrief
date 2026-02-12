const THEME_KEY = "arcbrief_theme";
const THEME_COOL = "cool";
const THEME_WARM = "warm";

function setTheme(theme) {
  const icon = document.getElementById("themeIcon");
  if (theme === THEME_COOL) {
    document.body.setAttribute("data-theme", THEME_COOL);
    if (icon) {
      icon.innerHTML =
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path>';
    }
  } else {
    document.body.removeAttribute("data-theme");
    if (icon) {
      icon.innerHTML =
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path>';
    }
  }
}

function toggleTheme() {
  const nextTheme =
    document.body.getAttribute("data-theme") === THEME_COOL
      ? THEME_WARM
      : THEME_COOL;
  setTheme(nextTheme);
  localStorage.setItem(THEME_KEY, nextTheme);
}

document.addEventListener("DOMContentLoaded", () => {
  const savedTheme = localStorage.getItem(THEME_KEY);
  setTheme(savedTheme === THEME_COOL ? THEME_COOL : THEME_WARM);
});
