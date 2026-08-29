(function () {
    "use strict";

    function each(selector, callback, root) {
        (root || document).querySelectorAll(selector).forEach(callback);
    }

    function initNavigation() {
        var toggle = document.querySelector("[data-mobile-nav-toggle]");
        var nav = document.querySelector(".site-nav");
        if (toggle && nav) {
            toggle.addEventListener("click", function () {
                var open = nav.classList.toggle("is-open");
                toggle.setAttribute("aria-expanded", String(open));
            });
            each(".site-nav a", function (link) {
                link.addEventListener("click", function () {
                    nav.classList.remove("is-open");
                    toggle.setAttribute("aria-expanded", "false");
                });
            });
        }

        var adminToggle = document.querySelector("[data-admin-menu-toggle]");
        var sidebar = document.querySelector("[data-admin-sidebar]");
        if (adminToggle && sidebar) {
            adminToggle.addEventListener("click", function () {
                var open = sidebar.classList.toggle("is-open");
                adminToggle.setAttribute("aria-expanded", String(open));
            });
            each(".admin-nav a", function (link) {
                link.addEventListener("click", function () {
                    sidebar.classList.remove("is-open");
                    adminToggle.setAttribute("aria-expanded", "false");
                });
            });
        }
    }

    function initProjectFilters() {
        var buttons = document.querySelectorAll("[data-project-filter]");
        var cards = document.querySelectorAll("[data-project-card]");
        if (!buttons.length || !cards.length) {
            return;
        }
        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                var filter = button.dataset.projectFilter;
                buttons.forEach(function (item) {
                    item.classList.toggle("is-selected", item === button);
                });
                cards.forEach(function (card) {
                    card.hidden = filter !== "all" && card.dataset.projectType !== filter;
                });
            });
        });
    }

    function initFileInputs() {
        each('input[type="file"]', function (input) {
            input.addEventListener("change", function () {
                var label = input.closest(".file-drop");
                if (!label) {
                    return;
                }
                var title = label.querySelector("strong");
                if (title && input.files.length) {
                    title.textContent = input.files.length === 1
                        ? input.files[0].name
                        : input.files.length + " files selected";
                }
            });
        });
    }

    function numberValue(input) {
        var value = Number.parseFloat(input && input.value);
        return Number.isFinite(value) ? value : 0;
    }

    function refreshEstimateTotal(form) {
        var total = 0;
        each("[data-form-row]", function (row) {
            var deleted = row.querySelector('input[name$="-DELETE"]');
            if (row.classList.contains("is-removed") || (deleted && deleted.checked)) {
                return;
            }
            total += numberValue(row.querySelector('input[name$="-quantity"]')) *
                numberValue(row.querySelector('input[name$="-unit_price"]'));
        }, form);
        var output = form.querySelector("[data-estimate-total]");
        if (output) {
            output.textContent = "$" + total.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }
    }

    function addEstimateRow(container) {
        var totalInput = document.getElementById(container.dataset.totalInput);
        if (!totalInput) {
            return;
        }
        var index = Number.parseInt(totalInput.value, 10) || 0;
        var row = document.createElement("div");
        row.className = "line-item-row estimate-line-grid";
        row.dataset.formRow = "";
        row.innerHTML =
            '<input type="hidden" name="lines-' + index + '-id" id="id_lines-' + index + '-id">' +
            '<label>Description<input type="text" name="lines-' + index + '-description" id="id_lines-' + index + '-description"></label>' +
            '<label>Qty<input type="number" name="lines-' + index + '-quantity" id="id_lines-' + index + '-quantity" min="0.01" step="0.01" value="1.00"></label>' +
            '<label>Unit price<input type="number" name="lines-' + index + '-unit_price" id="id_lines-' + index + '-unit_price" min="0" step="0.01" value="0.00"></label>' +
            '<input type="hidden" name="lines-' + index + '-sort_order" value="' + index + '">' +
            '<label class="remove-line-label"><input type="checkbox" name="lines-' + index + '-DELETE" value="on"> Remove</label>';
        container.appendChild(row);
        totalInput.value = String(index + 1);
        var form = container.closest("form");
        if (form) {
            refreshEstimateTotal(form);
        }
    }

    function initEstimateEditors() {
        each(".estimate-editor-form", function (form) {
            var container = form.querySelector(".estimate-line-items");
            if (!container) {
                return;
            }
            var addButton = document.createElement("button");
            addButton.type = "button";
            addButton.className = "button button-quiet add-line-item";
            addButton.textContent = "+ Add line item";
            addButton.addEventListener("click", function () {
                addEstimateRow(container);
            });
            var template = form.querySelector("[data-line-template]");
            if (template) {
                template.before(addButton);
            } else {
                container.after(addButton);
            }

            form.addEventListener("input", function (event) {
                if (event.target.matches('input[name$="-quantity"], input[name$="-unit_price"]')) {
                    refreshEstimateTotal(form);
                }
            });
            form.addEventListener("change", function (event) {
                if (event.target.matches('input[name$="-DELETE"]')) {
                    event.target.closest("[data-form-row]").classList.toggle("is-removed", event.target.checked);
                    refreshEstimateTotal(form);
                }
            });
            refreshEstimateTotal(form);
        });
    }

    function openModal(source) {
        var backdrop = document.querySelector("[data-modal]");
        var content = backdrop && backdrop.querySelector("[data-modal-content]");
        if (!backdrop || !content) {
            return;
        }
        var src = source.dataset.lightboxSrc;
        var alt = source.dataset.lightboxAlt || "Project media";
        content.innerHTML = '<img class="modal-image" src="' + src.replace(/"/g, "&quot;") + '" alt="' + alt.replace(/"/g, "&quot;") + '">';
        backdrop.hidden = false;
        document.body.classList.add("modal-open");
    }

    function closeModal() {
        var backdrop = document.querySelector("[data-modal]");
        if (!backdrop) {
            return;
        }
        backdrop.hidden = true;
        document.body.classList.remove("modal-open");
    }

    function initModal() {
        each(".js-lightbox", function (source) {
            source.addEventListener("click", function () {
                openModal(source);
            });
        });
        each('[data-action="close-modal"]', function (button) {
            button.addEventListener("click", closeModal);
        });
        var backdrop = document.querySelector("[data-modal]");
        if (backdrop) {
            backdrop.addEventListener("click", function (event) {
                if (event.target === backdrop) {
                    closeModal();
                }
            });
        }
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeModal();
            }
        });
    }

    function initToastDismissal() {
        window.setTimeout(function () {
            each(".toast", function (toast) {
                toast.style.opacity = "0";
                toast.style.transform = "translateY(9px)";
            });
        }, 7000);
    }

    function init() {
        initNavigation();
        initProjectFilters();
        initFileInputs();
        initEstimateEditors();
        initModal();
        initToastDismissal();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
