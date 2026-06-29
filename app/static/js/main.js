document.documentElement.classList.add("js-ready");

const sidebarStateKey = "locus.sidebarCollapsed";
const applySidebarState = (isCollapsed) => {
    document.body.classList.toggle("sidebar-collapsed", isCollapsed);
    const toggle = document.querySelector("[data-sidebar-toggle]");
    if (toggle) {
        toggle.setAttribute("aria-label", isCollapsed ? "Expand sidebar" : "Minimize sidebar");
        toggle.setAttribute("title", isCollapsed ? "Expand sidebar" : "Minimize sidebar");
    }
};

applySidebarState(localStorage.getItem(sidebarStateKey) === "true");

document.querySelector("[data-sidebar-toggle]")?.addEventListener("click", () => {
    const nextState = !document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem(sidebarStateKey, String(nextState));
    applySidebarState(nextState);
});
