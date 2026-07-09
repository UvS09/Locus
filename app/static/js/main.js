document.documentElement.classList.add("js-ready");

const sidebarStateKey = "locus.sidebarCollapsed";
const applySidebarState = (isCollapsed) => {
    document.body.classList.toggle("sidebar-collapsed", isCollapsed);
    const toggle = document.querySelector("[data-sidebar-toggle]");
    const icon = document.querySelector("[data-sidebar-toggle-icon]");
    if (toggle) {
        toggle.setAttribute("aria-label", isCollapsed ? "Expand navigation" : "Collapse navigation");
        toggle.setAttribute("title", isCollapsed ? "Expand navigation" : "Collapse navigation");
    }
    if (icon) {
        icon.className = `bi ${isCollapsed ? "bi-chevron-double-right" : "bi-chevron-double-left"}`;
    }
};

applySidebarState(localStorage.getItem(sidebarStateKey) === "true");

document.querySelector("[data-sidebar-toggle]")?.addEventListener("click", () => {
    const nextState = !document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem(sidebarStateKey, String(nextState));
    applySidebarState(nextState);
});

const progressiveForms = document.querySelectorAll("[data-user-form]");

const setFieldVisibility = (field, isVisible, { required = false } = {}) => {
    if (!field) return;
    field.classList.toggle("is-hidden-field", !isVisible);
    field.querySelectorAll("select, input, textarea").forEach((control) => {
        control.disabled = !isVisible;
        control.required = isVisible && required;
    });
};

const syncProgressiveUserForm = (form) => {
    const roleSelect = form.querySelector("[data-role-select]");
    const designationSelect = form.querySelector("[data-designation-select]");
    if (!roleSelect || !designationSelect) return;

    const roleSelected = Boolean(roleSelect.value);
    const selectedDesignation = designationSelect.options[designationSelect.selectedIndex];
    const scope = selectedDesignation?.dataset.scope || "";
    const hasDesignation = roleSelected && Boolean(designationSelect.value);

    setFieldVisibility(form.querySelector('[data-stage="designation"]'), roleSelected, { required: true });
    setFieldVisibility(form.querySelector('[data-stage="division"]'), hasDesignation && ["DIVISION_HEAD", "DEPARTMENT_HEAD", "TEAM_MEMBER"].includes(scope), { required: true });
    setFieldVisibility(form.querySelector('[data-stage="department"]'), hasDesignation && ["DEPARTMENT_HEAD", "TEAM_MEMBER"].includes(scope), { required: true });
}

progressiveForms.forEach((form) => {
    const roleSelect = form.querySelector("[data-role-select]");
    const designationSelect = form.querySelector("[data-designation-select]");
    roleSelect?.addEventListener("change", () => {
        if (designationSelect && !designationSelect.value) {
            designationSelect.selectedIndex = 0;
        }
        syncProgressiveUserForm(form);
    });
    designationSelect?.addEventListener("change", () => syncProgressiveUserForm(form));
    syncProgressiveUserForm(form);
});

const orgCreateForms = document.querySelectorAll("[data-org-create-form]");

const syncOrgCreateForm = (form) => {
    const typeSelect = form.querySelector("[data-org-type]");
    const type = typeSelect?.value || "";
    const divisionField = form.querySelector("[data-org-division]");
    const departmentField = form.querySelector("[data-org-department]");
    const managerField = form.querySelector("[data-org-manager]");

    if (divisionField) {
        divisionField.classList.toggle("is-hidden-field", !["department", "team"].includes(type));
        divisionField.disabled = !["department", "team"].includes(type);
        divisionField.required = type === "department";
    }
    if (departmentField) {
        departmentField.classList.toggle("is-hidden-field", type !== "team");
        departmentField.disabled = type !== "team";
        departmentField.required = type === "team";
    }
    if (managerField) {
        managerField.classList.toggle("is-hidden-field", type !== "team");
        managerField.disabled = type !== "team";
        managerField.required = false;
    }
};

orgCreateForms.forEach((form) => {
    form.querySelector("[data-org-type]")?.addEventListener("change", () => syncOrgCreateForm(form));
    syncOrgCreateForm(form);
});

const passwordRuleInputs = document.querySelectorAll("[data-password-rules]");
const passwordRuleMessage = "Use at least 8 characters with uppercase, lowercase, number, and special character.";

const validatePasswordRules = (input) => {
    const value = input.value || "";
    const isValid = (
        value.length >= 8 &&
        /[a-z]/.test(value) &&
        /[A-Z]/.test(value) &&
        /[0-9]/.test(value) &&
        /[^A-Za-z0-9]/.test(value)
    );
    input.setCustomValidity(value && !isValid ? passwordRuleMessage : "");
};

passwordRuleInputs.forEach((input) => {
    input.addEventListener("input", () => validatePasswordRules(input));
    input.addEventListener("invalid", () => validatePasswordRules(input));
});
