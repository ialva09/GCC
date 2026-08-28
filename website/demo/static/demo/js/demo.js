(function () {
    "use strict";

    var STORAGE_KEY = "gcc-demo-state-v1";
    var ASSET_ROOT = (document.body.dataset.assetRoot || "/static/demo/").replace(/\/?$/, "/");
    var ADMIN_SECTIONS = ["overview", "leads", "estimates", "projects", "media", "content"];
    var STATUS_ORDER = ["New", "Contacted", "Qualified", "Quoted", "Won", "Lost"];
    var estimateStatuses = ["Draft", "Sent", "Accepted", "Declined"];
    var projectStatuses = ["Planning", "Selections", "Construction", "Final walkthrough", "Complete", "On hold"];

    var seedState = {
        leads: [
            { id: "lead-001", name: "Maya Thompson", service: "Renovations", location: "Ventura, CA", email: "maya.thompson@example.com", phone: "(805) 555-0148", status: "Qualified", priority: true, budget: "$40k–$55k", timeline: "Start in 4–6 weeks", source: "Website form", note: "Wants a calmer kitchen layout with durable, family-friendly finishes.", followUps: [{ id: "followup-001", title: "Review finish direction", due: "Tomorrow", done: false }] },
            { id: "lead-002", name: "James & Ana Rivera", service: "Residential Construction", location: "Camarillo, CA", email: "rivera.family@example.com", phone: "(805) 555-0162", status: "New", priority: false, budget: "$85k–$120k", timeline: "This summer", source: "Referral", note: "Exploring a backyard ADU for family visits and long-term flexibility.", followUps: [] },
            { id: "lead-003", name: "Miguel Santos", service: "Restoration", location: "Oxnard, CA", email: "miguel.santos@example.com", phone: "(805) 555-0174", status: "Contacted", priority: false, budget: "$25k–$40k", timeline: "As soon as possible", source: "Google search", note: "Needs an initial assessment after water damage in the lower level.", followUps: [{ id: "followup-002", title: "Confirm site visit", due: "Friday", done: false }] },
            { id: "lead-004", name: "Harbor Studio", service: "Commercial Construction", location: "Santa Barbara, CA", email: "hello@harborstudio.example.com", phone: "(805) 555-0183", status: "Quoted", priority: true, budget: "$140k–$175k", timeline: "Q4 2026", source: "Partner referral", note: "Small creative studio build-out with a flexible client meeting room.", followUps: [] },
            { id: "lead-005", name: "Priya Patel", service: "Custom Homes", location: "Ojai, CA", email: "priya.patel@example.com", phone: "(805) 555-0191", status: "Won", priority: false, budget: "$420k+", timeline: "Planning phase", source: "Past client", note: "Early planning for a compact, light-filled custom home.", followUps: [] },
            { id: "lead-006", name: "North Shore Foods", service: "Project Management", location: "Ventura, CA", email: "ops@northshorefoods.example.com", phone: "(805) 555-0198", status: "New", priority: false, budget: "$60k–$90k", timeline: "Next 90 days", source: "Website form", note: "Looking for owner-side coordination on a small restaurant refresh.", followUps: [] }
        ],
        estimates: [
            { id: "estimate-001", number: "1048", leadId: "lead-001", title: "Coastal Kitchen Renovation", client: "Maya Thompson", status: "Sent", deposit: 9720, created: "Aug 24, 2026" },
            { id: "estimate-002", number: "1047", leadId: "lead-004", title: "Harbor Studio Build-out", client: "Harbor Studio", status: "Draft", deposit: 28000, created: "Aug 21, 2026" },
            { id: "estimate-003", number: "1042", leadId: "lead-005", title: "Ojai Custom Home Planning", client: "Priya Patel", status: "Accepted", deposit: 84000, created: "Aug 08, 2026" }
        ],
        estimateLineItems: [
            { id: "line-001", estimateId: "estimate-001", description: "Cabinetry, demo & prep", amount: 24000 },
            { id: "line-002", estimateId: "estimate-001", description: "Electrical & plumbing", amount: 6800 },
            { id: "line-003", estimateId: "estimate-001", description: "Surfaces & fixtures", amount: 9200 },
            { id: "line-004", estimateId: "estimate-001", description: "Project management", amount: 8600 },
            { id: "line-005", estimateId: "estimate-002", description: "Selective demo & prep", amount: 18000 },
            { id: "line-006", estimateId: "estimate-002", description: "Partitions & finishes", amount: 52000 },
            { id: "line-007", estimateId: "estimate-002", description: "Lighting & millwork", amount: 23000 },
            { id: "line-008", estimateId: "estimate-003", description: "Pre-construction planning", amount: 42000 },
            { id: "line-009", estimateId: "estimate-003", description: "Site coordination", amount: 188000 },
            { id: "line-010", estimateId: "estimate-003", description: "Design-build management", amount: 105000 }
        ],
        projects: [
            { id: "project-001", estimateId: "estimate-001", leadId: "lead-001", title: "Coastal Kitchen Renovation", location: "Ventura, CA", status: "Planning", nextStep: "Review finish selections", cover: "images/progress-kitchen.png" },
            { id: "project-002", estimateId: "estimate-003", leadId: "lead-005", title: "Ojai Custom Home Planning", location: "Ojai, CA", status: "Selections", nextStep: "Finalize schematic set", cover: "images/project-adu.png" },
            { id: "project-003", estimateId: null, leadId: "lead-004", title: "Harbor Studio Build-out", location: "Santa Barbara, CA", status: "Construction", nextStep: "Electrical rough-in", cover: "images/project-bathroom.png" },
            { id: "project-004", estimateId: null, leadId: "lead-005", title: "Quiet Bathroom Retreat", location: "Oxnard, CA", status: "Complete", nextStep: "Final walkthrough complete", cover: "images/project-bathroom.png" }
        ],
        milestones: [
            { id: "milestone-001", projectId: "project-001", title: "Walkthrough", complete: true },
            { id: "milestone-002", projectId: "project-001", title: "Estimate approved", complete: true },
            { id: "milestone-003", projectId: "project-001", title: "Selections", complete: false },
            { id: "milestone-004", projectId: "project-001", title: "Construction", complete: false },
            { id: "milestone-005", projectId: "project-001", title: "Final walkthrough", complete: false },
            { id: "milestone-006", projectId: "project-002", title: "Walkthrough", complete: true },
            { id: "milestone-007", projectId: "project-002", title: "Estimate approved", complete: true },
            { id: "milestone-008", projectId: "project-002", title: "Selections", complete: true },
            { id: "milestone-009", projectId: "project-002", title: "Construction", complete: false },
            { id: "milestone-010", projectId: "project-002", title: "Final walkthrough", complete: false },
            { id: "milestone-011", projectId: "project-003", title: "Walkthrough", complete: true },
            { id: "milestone-012", projectId: "project-003", title: "Estimate approved", complete: true },
            { id: "milestone-013", projectId: "project-003", title: "Selections", complete: true },
            { id: "milestone-014", projectId: "project-003", title: "Construction", complete: true },
            { id: "milestone-015", projectId: "project-003", title: "Final walkthrough", complete: false },
            { id: "milestone-016", projectId: "project-004", title: "Walkthrough", complete: true },
            { id: "milestone-017", projectId: "project-004", title: "Estimate approved", complete: true },
            { id: "milestone-018", projectId: "project-004", title: "Selections", complete: true },
            { id: "milestone-019", projectId: "project-004", title: "Construction", complete: true },
            { id: "milestone-020", projectId: "project-004", title: "Final walkthrough", complete: true }
        ],
        projectUpdates: [
            { id: "update-001", projectId: "project-001", title: "Material selections are next.", body: "We’ve completed the walkthrough and are ready to review finishes with you.", visible: true, time: "Today · 9:42 AM" },
            { id: "update-002", projectId: "project-001", title: "Walkthrough notes are organized.", body: "The scope is shaped and the next step is a focused finish review.", visible: false, time: "Yesterday · 3:18 PM" },
            { id: "update-003", projectId: "project-002", title: "Schematic set is taking shape.", body: "The team is reviewing the latest plan against the site priorities.", visible: true, time: "Aug 25 · 11:10 AM" },
            { id: "update-004", projectId: "project-003", title: "Rough-in is underway.", body: "Electrical and plumbing coordination is moving through the studio build-out.", visible: true, time: "Aug 22 · 2:05 PM" }
        ],
        media: [
            { id: "media-001", projectId: "project-001", title: "Kitchen progress", type: "photo", src: "images/progress-kitchen.png", visibility: "client", caption: "Protected floors are down and the rough-in is ready for the next review." },
            { id: "media-002", projectId: "project-001", title: "Design direction", type: "photo", src: "images/hero-kitchen.png", visibility: "public", caption: "Warm materials and an open plan for everyday life." },
            { id: "media-003", projectId: "project-001", title: "Finish review clip", type: "video", src: "images/project-bathroom.png", visibility: "internal", caption: "Demo video thumbnail for the finish review." },
            { id: "media-004", projectId: "project-002", title: "Entry study", type: "photo", src: "images/project-adu.png", visibility: "public", caption: "A compact California addition with a welcoming entry." },
            { id: "media-005", projectId: "project-003", title: "Material palette", type: "photo", src: "images/project-bathroom.png", visibility: "client", caption: "Deep blue cabinetry with warm metal details." },
            { id: "media-006", projectId: "project-003", title: "Internal site note", type: "photo", src: "images/progress-kitchen.png", visibility: "internal", caption: "Internal-only jobsite reference." }
        ],
        activities: [
            { id: "activity-001", text: "Estimate #1048 is ready for Maya Thompson", detail: "Coastal Kitchen Renovation · 14 minutes ago" },
            { id: "activity-002", text: "Harbor Studio moved to Quoted", detail: "Lead pipeline · 1 hour ago" },
            { id: "activity-003", text: "New progress photo added", detail: "Coastal Kitchen Renovation · Yesterday" },
            { id: "activity-004", text: "Ojai Custom Home Planning accepted", detail: "Estimate #1042 · Yesterday" },
            { id: "activity-005", text: "Walkthrough notes added", detail: "Coastal Kitchen Renovation · Aug 25" }
        ],
        siteContent: {
            headline: "Build with confidence.",
            subheadline: "Thoughtful construction, clear communication, and a better experience from first walkthrough to final handoff.",
            featuredTitle: "Coastal Bathroom Renovation",
            featuredBody: "A calm, highly functional renovation shaped around durable materials, thoughtful storage, and the small details that make a space feel finished.",
            step1: "Walkthrough",
            step2: "Estimate",
            step3: "Build",
            step4: "Handoff",
            services: [
                { id: "residential", title: "Residential Construction", copy: "New additions, ADUs, and ground-up construction tailored to your home." },
                { id: "renovations", title: "Renovations", copy: "Kitchens, bathrooms, and whole-home improvements with a clear plan." },
                { id: "restoration", title: "Restoration", copy: "Repairs and rebuilding after water, fire, or structural damage." },
                { id: "commercial", title: "Commercial Construction", copy: "Tenant improvements, build-outs, and small commercial projects." },
                { id: "management", title: "Project Management", copy: "Scope, communication, and oversight from start to finish." },
                { id: "custom", title: "Custom Homes", copy: "Design and build your custom home with care and attention to detail." }
            ]
        },
        portal: {
            projectId: "project-001",
            estimateId: "estimate-001",
            paymentStatus: "Not paid yet"
        }
    };

    var state = loadState();
    var adminRoot = document.querySelector("[data-admin-root]");
    var adminSection = adminRoot ? (adminRoot.dataset.initialSection || "overview") : "overview";
    var selectedLeadId = state.leads[0] ? state.leads[0].id : null;
    var selectedEstimateId = state.estimates[0] ? state.estimates[0].id : null;
    var selectedProjectId = state.projects[0] ? state.projects[0].id : null;
    var mediaFilter = "all";
    var mediaProjectFilter = "all";

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function loadState() {
        var fallback = clone(seedState);
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return fallback;
            }
            var saved = JSON.parse(raw);
            Object.keys(fallback).forEach(function (key) {
                if (saved[key] !== undefined) {
                    fallback[key] = saved[key];
                }
            });
            return fallback;
        } catch (error) {
            return fallback;
        }
    }

    function saveState() {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            return true;
        } catch (error) {
            return false;
        }
    }

    function nextId(prefix) {
        return prefix + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
    }

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function money(value) {
        var amount = Number(value) || 0;
        return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
    }

    function numeric(value) {
        var parsed = Number.parseFloat(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function asset(path) {
        if (!path) {
            return "";
        }
        if (/^(data:|https?:|\/)/i.test(path)) {
            return path;
        }
        return ASSET_ROOT + path.replace(/^\/+/, "");
    }

    function byId(collection, id) {
        return (state[collection] || []).find(function (record) { return record.id === id; });
    }

    function estimateItems(estimateId) {
        return state.estimateLineItems.filter(function (item) { return item.estimateId === estimateId; });
    }

    function estimateTotal(estimateId) {
        return estimateItems(estimateId).reduce(function (total, item) { return total + numeric(item.amount); }, 0);
    }

    function projectMilestones(projectId) {
        return state.milestones.filter(function (item) { return item.projectId === projectId; });
    }

    function projectUpdates(projectId) {
        return state.projectUpdates.filter(function (item) { return item.projectId === projectId; });
    }

    function projectProgress(projectId) {
        var milestones = projectMilestones(projectId);
        if (!milestones.length) {
            return 0;
        }
        return Math.round((milestones.filter(function (item) { return item.complete; }).length / milestones.length) * 100);
    }

    function statusClass(status) {
        if (["Accepted", "Won", "Complete"].indexOf(status) !== -1) {
            return "green";
        }
        if (["Quoted", "Sent", "Final walkthrough"].indexOf(status) !== -1) {
            return "gold";
        }
        if (["Lost", "Declined"].indexOf(status) !== -1) {
            return "red";
        }
        return "";
    }

    function toast(message) {
        var region = document.querySelector("[data-toast-region]");
        if (!region) {
            return;
        }
        var item = document.createElement("div");
        item.className = "toast";
        item.textContent = message;
        region.appendChild(item);
        window.setTimeout(function () {
            item.style.opacity = "0";
            item.style.transform = "translateY(5px)";
            window.setTimeout(function () { item.remove(); }, 240);
        }, 3200);
    }

    function modalContent() {
        return document.querySelector("[data-modal-content]");
    }

    function openModal(html) {
        var backdrop = document.querySelector("[data-modal]");
        var content = modalContent();
        if (!backdrop || !content) {
            return;
        }
        content.innerHTML = html;
        backdrop.hidden = false;
        document.body.classList.add("no-scroll");
        var focusable = content.querySelector("input, select, textarea, button");
        if (focusable) {
            window.setTimeout(function () { focusable.focus(); }, 20);
        }
    }

    function closeModal() {
        var backdrop = document.querySelector("[data-modal]");
        if (backdrop) {
            backdrop.hidden = true;
        }
        document.body.classList.remove("no-scroll");
    }

    function recordActivity(text, detail) {
        state.activities.unshift({ id: nextId("activity"), text: text, detail: detail || "Owner workspace · just now" });
        state.activities = state.activities.slice(0, 18);
        saveState();
    }

    function setText(selector, value) {
        document.querySelectorAll(selector).forEach(function (element) {
            element.textContent = value;
        });
    }

    function applySiteContent() {
        var content = state.siteContent;
        var fieldMap = {
            headline: content.headline,
            subheadline: content.subheadline,
            featuredTitle: content.featuredTitle,
            featuredBody: content.featuredBody
        };
        Object.keys(fieldMap).forEach(function (key) {
            setText("[data-site-field='" + key + "']", fieldMap[key]);
        });
        (content.services || []).forEach(function (service) {
            setText("[data-service-title='" + service.id + "']", service.title);
            setText("[data-service-copy='" + service.id + "']", service.copy);
        });
        ["step1", "step2", "step3", "step4"].forEach(function (key) {
            setText("[data-process-step='" + key + "']", content[key]);
        });
    }

    function initPublicSite() {
        applySiteContent();
        var navToggle = document.querySelector("[data-mobile-nav-toggle]");
        var nav = document.querySelector(".site-nav");
        if (navToggle && nav) {
            navToggle.addEventListener("click", function () {
                var open = nav.classList.toggle("is-open");
                navToggle.setAttribute("aria-expanded", String(open));
            });
            nav.addEventListener("click", function (event) {
                if (event.target.closest("a")) {
                    nav.classList.remove("is-open");
                    navToggle.setAttribute("aria-expanded", "false");
                }
            });
        }
        document.querySelectorAll("[data-estimate-form]").forEach(function (form) {
            if (form.closest("[data-admin-root]")) {
                return;
            }
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                var success = form.querySelector("[data-form-success]");
                if (success) {
                    success.hidden = false;
                }
                var button = form.querySelector("button[type=submit]");
                if (button) {
                    button.disabled = true;
                    button.textContent = "Request captured in demo ✓";
                }
                toast("Demo request captured locally — nothing was sent.");
            });
        });
        document.querySelectorAll("[data-demo-file]").forEach(function (input) {
            input.addEventListener("change", function () {
                var label = input.closest(".file-drop");
                var small = label ? label.querySelector("small") : null;
                if (small && input.files.length) {
                    small.textContent = input.files.length + " demo file" + (input.files.length === 1 ? "" : "s") + " selected · Nothing uploads";
                }
            });
        });
    }

    function renderPublicProjectFilters() {
        var cards = document.querySelectorAll("[data-project-card]");
        if (!cards.length) {
            return;
        }
        var selected = document.querySelector("[data-project-filter].is-selected");
        var filter = selected ? selected.dataset.projectFilter : "all";
        cards.forEach(function (card) {
            card.hidden = filter !== "all" && card.dataset.projectType !== filter;
        });
    }

    function initPublicProjectFilters() {
        document.addEventListener("click", function (event) {
            var filterButton = event.target.closest("[data-project-filter]");
            if (!filterButton) {
                return;
            }
            event.preventDefault();
            document.querySelectorAll("[data-project-filter]").forEach(function (button) { button.classList.remove("is-selected"); });
            filterButton.classList.add("is-selected");
            renderPublicProjectFilters();
        });
        renderPublicProjectFilters();
    }

    function renderStats() {
        if (!adminRoot) {
            return;
        }
        var openLeads = state.leads.filter(function (lead) { return ["Won", "Lost"].indexOf(lead.status) === -1; }).length;
        var pendingEstimates = state.estimates.filter(function (estimate) { return ["Draft", "Sent"].indexOf(estimate.status) !== -1; }).length;
        var activeProjects = state.projects.filter(function (project) { return project.status !== "Complete"; }).length;
        setText("[data-stat='open-leads']", openLeads);
        setText("[data-stat='pending-estimates']", pendingEstimates);
        setText("[data-stat='active-projects']", activeProjects);
        setText("[data-nav-count='leads']", openLeads);
        setText("[data-nav-count='estimates']", pendingEstimates);
        setText("[data-nav-count='projects']", activeProjects);
    }

    function renderPipeline() {
        var board = document.querySelector("[data-pipeline]");
        if (!board) {
            return;
        }
        var columns = [
            { title: "New", statuses: ["New"] },
            { title: "In conversation", statuses: ["Contacted", "Qualified"] },
            { title: "Quoted", statuses: ["Quoted"] },
            { title: "Won", statuses: ["Won"], won: true }
        ];
        board.innerHTML = columns.map(function (column) {
            var leads = state.leads.filter(function (lead) { return column.statuses.indexOf(lead.status) !== -1; });
            return "<div class=\"pipeline-column" + (column.won ? " is-won" : "") + "\">" +
                "<div class=\"pipeline-column-title\"><span>" + esc(column.title) + "</span><span>" + leads.length + "</span></div>" +
                (leads.length ? leads.map(function (lead) {
                    return "<button class=\"pipeline-card\" type=\"button\" data-lead-record=\"" + esc(lead.id) + "\"><strong>" + esc(lead.name) + (lead.priority ? " ★" : "") + "</strong><small>" + esc(lead.service) + "</small><span>" + esc(lead.location) + "</span></button>";
                }).join("") : "<div class=\"empty-detail\" style=\"min-height:80px;\">No leads here yet.</div>") +
                "</div>";
        }).join("");
    }

    function renderOverviewProjects() {
        var body = document.querySelector("[data-overview-projects]");
        if (!body) {
            return;
        }
        var projects = state.projects.filter(function (project) { return project.status !== "Complete"; }).slice(0, 4);
        body.innerHTML = projects.map(function (project) {
            return "<tr><td>" + esc(project.title) + "</td><td><span class=\"status-badge " + statusClass(project.status) + "\">" + esc(project.status) + "</span></td><td>" + esc(project.nextStep) + "</td><td>" + projectProgress(project.id) + "%</td></tr>";
        }).join("");
    }

    function renderActivities() {
        var list = document.querySelector("[data-activity-list]");
        if (!list) {
            return;
        }
        list.innerHTML = state.activities.slice(0, 7).map(function (activity) {
            return "<div class=\"activity-item\"><span class=\"activity-dot\"></span><div><strong>" + esc(activity.text) + "</strong><small>" + esc(activity.detail) + "</small></div></div>";
        }).join("");
    }

    function leadMatches(lead, query, filter) {
        var haystack = [lead.name, lead.service, lead.location].join(" ").toLowerCase();
        return (!query || haystack.indexOf(query.toLowerCase()) !== -1) && (filter === "all" || lead.status === filter);
    }

    function renderLeadList() {
        var list = document.querySelector("[data-leads-list]");
        if (!list) {
            return;
        }
        var search = document.querySelector("[data-lead-search]");
        var filter = document.querySelector("[data-lead-filter]");
        var query = search ? search.value.trim() : "";
        var status = filter ? filter.value : "all";
        var leads = state.leads.filter(function (lead) { return leadMatches(lead, query, status); });
        var html = "<div class=\"record-list-header\"><span>Lead</span><span>Stage</span><span>Added</span></div>";
        html += leads.length ? leads.map(function (lead) {
            return "<button class=\"record-row" + (lead.id === selectedLeadId ? " is-selected" : "") + "\" type=\"button\" data-lead-record=\"" + esc(lead.id) + "\"><span class=\"record-row-grid\"><span><strong>" + esc(lead.name) + (lead.priority ? " <span style=\"color:var(--brand-gold);\">★</span>" : "") + "</strong><small>" + esc(lead.service) + " · " + esc(lead.location) + "</small></span><span><span class=\"status-badge " + statusClass(lead.status) + "\">" + esc(lead.status) + "</span></span><span class=\"record-date\">" + esc(lead.source) + "</span></span></button>";
        }).join("") : "<div class=\"empty-detail\">No leads match these filters.</div>";
        list.innerHTML = html;
    }

    function renderLeadDetail() {
        var detail = document.querySelector("[data-lead-detail]");
        if (!detail) {
            return;
        }
        var lead = byId("leads", selectedLeadId);
        if (!lead) {
            detail.innerHTML = "<div class=\"empty-detail\">Select a lead to see the conversation.</div>";
            return;
        }
        var estimate = state.estimates.find(function (item) { return item.leadId === lead.id; });
        var relatedActivities = state.activities.filter(function (activity) {
            return activity.text.toLowerCase().indexOf(lead.name.split(" ")[0].toLowerCase()) !== -1 ||
                activity.detail.toLowerCase().indexOf(lead.service.split(" ")[0].toLowerCase()) !== -1;
        }).slice(0, 3);
        detail.innerHTML =
            "<div class=\"detail-header\"><div><span class=\"section-kicker\">Lead record</span><h3>" + esc(lead.name) + "</h3><p>" + esc(lead.service) + " · " + esc(lead.location) + "</p></div><button class=\"priority-toggle" + (lead.priority ? " is-priority" : "") + "\" type=\"button\" data-action=\"toggle-priority\" data-lead-id=\"" + esc(lead.id) + "\"><span class=\"priority-star\">★</span>" + (lead.priority ? " Priority" : " Mark priority") + "</button></div>" +
            "<div class=\"detail-actions\">" +
            (estimate ? "<button class=\"button button-primary\" type=\"button\" data-action=\"open-estimate\" data-estimate-id=\"" + esc(estimate.id) + "\">Open estimate #" + esc(estimate.number) + "</button>" : "<button class=\"button button-primary\" type=\"button\" data-action=\"convert-lead\" data-lead-id=\"" + esc(lead.id) + "\">Create estimate</button>") +
            "<button class=\"button button-outline\" type=\"button\" data-action=\"add-followup\" data-lead-id=\"" + esc(lead.id) + "\">Add follow-up</button><button class=\"button button-quiet\" type=\"button\" data-action=\"schedule-walkthrough\" data-lead-id=\"" + esc(lead.id) + "\">Schedule walkthrough</button></div>" +
            "<div class=\"detail-tabs\"><button class=\"detail-tab is-current\" type=\"button\">Details</button><button class=\"detail-tab\" type=\"button\" data-action=\"lead-notes-tab\">Notes & follow-ups</button></div>" +
            "<div class=\"detail-columns\"><div><span class=\"detail-label\">Status</span><div class=\"inline-control\"><select data-lead-status data-lead-id=\"" + esc(lead.id) + "\">" + STATUS_ORDER.map(function (item) { return "<option" + (item === lead.status ? " selected" : "") + ">" + item + "</option>"; }).join("") + "</select></div><span class=\"detail-label\" style=\"margin-top:19px;\">Contact</span><span class=\"detail-value\">" + esc(lead.email) + "<br>" + esc(lead.phone) + "</span><span class=\"detail-label\">Budget / timing</span><span class=\"detail-value\">" + esc(lead.budget) + "<br>" + esc(lead.timeline) + "</span><span class=\"detail-label\">Source</span><span class=\"detail-value\">" + esc(lead.source) + "</span></div>" +
            "<div><span class=\"detail-label\">Working note</span><p class=\"detail-value\">" + esc(lead.note || "No note added yet.") + "</p><form class=\"note-form\" data-lead-note-form data-lead-id=\"" + esc(lead.id) + "\"><textarea name=\"note\" placeholder=\"Add a note for the next conversation...\"></textarea><button type=\"submit\">Save note</button></form><span class=\"detail-label\" style=\"margin-top:24px;\">Follow-up tasks</span>" +
            (lead.followUps && lead.followUps.length ? "<div class=\"mini-activity\">" + lead.followUps.map(function (task) { return "<div class=\"mini-activity-item\"><i></i><div><strong>" + esc(task.title) + "</strong><small>" + esc(task.due) + (task.done ? " · Done" : " · Open") + "</small></div></div>"; }).join("") + "</div>" : "<p class=\"detail-value\">No follow-up tasks yet.</p>") +
            "<span class=\"detail-label\" style=\"margin-top:24px;\">Recent activity</span><div class=\"mini-activity\">" + (relatedActivities.length ? relatedActivities.map(function (activity) { return "<div class=\"mini-activity-item\"><i></i><div><strong>" + esc(activity.text) + "</strong><small>" + esc(activity.detail) + "</small></div></div>"; }).join("") : "<p class=\"detail-value\">No related activity yet.</p>") + "</div></div></div>";
    }

    function renderLeads() {
        renderLeadList();
        renderLeadDetail();
    }

    function renderEstimateList() {
        var list = document.querySelector("[data-estimates-list]");
        if (!list) {
            return;
        }
        var html = "<div class=\"record-list-header\"><span>Estimate</span><span>Status</span><span>Total</span></div>";
        html += state.estimates.length ? state.estimates.map(function (estimate) {
            return "<button class=\"record-row" + (estimate.id === selectedEstimateId ? " is-selected" : "") + "\" type=\"button\" data-estimate-record=\"" + esc(estimate.id) + "\"><span class=\"record-row-grid\"><span><strong>#" + esc(estimate.number) + " · " + esc(estimate.title) + "</strong><small>" + esc(estimate.client) + " · " + esc(estimate.created) + "</small></span><span><span class=\"status-badge " + statusClass(estimate.status) + "\">" + esc(estimate.status) + "</span></span><span class=\"record-date\">" + money(estimateTotal(estimate.id)) + "</span></span></button>";
        }).join("") : "<div class=\"empty-detail\">No estimates yet.</div>";
        list.innerHTML = html;
    }

    function editorTotal(form) {
        var total = 0;
        form.querySelectorAll("[data-line-amount]").forEach(function (input) {
            total += numeric(input.value);
        });
        var totalNode = form.querySelector("[data-estimate-total]");
        if (totalNode) {
            totalNode.textContent = money(total);
        }
        var depositNode = form.querySelector("[data-estimate-deposit-copy]");
        if (depositNode) {
            var depositInput = form.querySelector("[name=deposit]");
            depositNode.textContent = "Deposit preview · " + money(numeric(depositInput ? depositInput.value : 0));
        }
        return total;
    }

    function renderEstimateEditor() {
        var editor = document.querySelector("[data-estimate-editor]");
        if (!editor) {
            return;
        }
        var estimate = byId("estimates", selectedEstimateId);
        if (!estimate) {
            editor.innerHTML = "<div class=\"empty-detail\">Select an estimate to edit its scope.</div>";
            return;
        }
        var linkedLead = byId("leads", estimate.leadId);
        var project = state.projects.find(function (item) { return item.estimateId === estimate.id; });
        editor.innerHTML =
            "<div class=\"detail-header\"><div><span class=\"section-kicker\">Estimate #" + esc(estimate.number) + "</span><h3>" + esc(estimate.title) + "</h3><p>" + esc(estimate.client) + (linkedLead ? " · " + esc(linkedLead.location) : "") + "</p></div><span class=\"status-badge " + statusClass(estimate.status) + "\">" + esc(estimate.status) + "</span></div>" +
            "<form class=\"estimate-editor-form\" data-estimate-editor-form data-estimate-id=\"" + esc(estimate.id) + "\"><div class=\"detail-columns\"><label>Customer / organization<input name=\"client\" value=\"" + esc(estimate.client) + "\"></label><label>Estimate title<input name=\"title\" value=\"" + esc(estimate.title) + "\"></label></div><div class=\"detail-columns\"><label>Status<select name=\"status\" data-estimate-status>" + estimateStatuses.map(function (status) { return "<option" + (status === estimate.status ? " selected" : "") + ">" + status + "</option>"; }).join("") + "</select></label><label>Deposit amount<input type=\"number\" min=\"0\" step=\"100\" name=\"deposit\" value=\"" + esc(estimate.deposit) + "\"></label></div><div class=\"admin-section-heading compact\" style=\"margin-top:18px;\"><div><span class=\"section-kicker\">Scope</span><h4 style=\"margin:0;color:var(--brand-navy);\">Line items</h4></div><button class=\"button button-quiet\" type=\"button\" data-action=\"add-line-item\" data-estimate-id=\"" + esc(estimate.id) + "\">+ Add line item</button></div><div class=\"estimate-line-items\">" +
            estimateItems(estimate.id).map(function (item) { return "<div class=\"line-item-row\"><input aria-label=\"Line item description\" data-line-description data-line-id=\"" + esc(item.id) + "\" value=\"" + esc(item.description) + "\"><input aria-label=\"Line item amount\" type=\"number\" min=\"0\" step=\"100\" data-line-amount data-line-id=\"" + esc(item.id) + "\" value=\"" + esc(item.amount) + "\"><button class=\"remove-line\" type=\"button\" aria-label=\"Remove line item\" data-action=\"remove-line-item\" data-line-id=\"" + esc(item.id) + "\" data-estimate-id=\"" + esc(estimate.id) + "\">×</button></div>"; }).join("") +
            "</div><div class=\"estimate-totals\"><span>Estimated project total</span><strong data-estimate-total>" + money(estimateTotal(estimate.id)) + "</strong><span>Deposit</span><span data-estimate-deposit-copy>" + money(estimate.deposit) + "</span></div><div class=\"estimate-editor-footer\"><span style=\"color:var(--muted);font-size:.62rem;\">" + (project ? "Converted to " + esc(project.title) : "Changes are local until a real workflow is connected.") + "</span><span class=\"detail-actions\" style=\"margin:0;\"><button class=\"button button-quiet\" type=\"button\" data-action=\"preview-estimate\" data-estimate-id=\"" + esc(estimate.id) + "\">Preview</button><button class=\"button button-outline\" type=\"button\" data-action=\"send-estimate\" data-estimate-id=\"" + esc(estimate.id) + "\">Simulate send</button>" + (estimate.status === "Accepted" ? (project ? "<button class=\"button button-primary\" type=\"button\" data-action=\"open-project\" data-project-id=\"" + esc(project.id) + "\">Open project</button>" : "<button class=\"button button-primary\" type=\"button\" data-action=\"convert-estimate\" data-estimate-id=\"" + esc(estimate.id) + "\">Create project</button>") : "<button class=\"button button-primary\" type=\"submit\">Save changes</button>") + "</span></div></form>";
        var form = editor.querySelector("[data-estimate-editor-form]");
        if (form) {
            editorTotal(form);
        }
    }

    function renderProjectsList() {
        var list = document.querySelector("[data-projects-list]");
        if (!list) {
            return;
        }
        var html = "<div class=\"record-list-header\"><span>Project</span><span>Stage</span><span>Progress</span></div>";
        html += state.projects.length ? state.projects.map(function (project) {
            return "<button class=\"record-row project-list-row" + (project.id === selectedProjectId ? " is-selected" : "") + "\" type=\"button\" data-project-record=\"" + esc(project.id) + "\"><span class=\"record-row-grid\"><span><strong>" + esc(project.title) + "</strong><small>" + esc(project.location) + "</small></span><span><span class=\"status-badge " + statusClass(project.status) + "\">" + esc(project.status) + "</span></span><span class=\"record-date\">" + projectProgress(project.id) + "%</span></span></button>";
        }).join("") : "<div class=\"empty-detail\">No projects yet.</div>";
        list.innerHTML = html;
    }

    function renderProjectEditor() {
        var editor = document.querySelector("[data-project-editor]");
        if (!editor) {
            return;
        }
        var project = byId("projects", selectedProjectId);
        if (!project) {
            editor.innerHTML = "<div class=\"empty-detail\">Select a project to see delivery details.</div>";
            return;
        }
        var milestones = projectMilestones(project.id);
        var updates = projectUpdates(project.id);
        var progress = projectProgress(project.id);
        editor.innerHTML =
            "<img class=\"project-cover\" src=\"" + esc(asset(project.cover)) + "\" alt=\"Project preview for " + esc(project.title) + "\"><div class=\"detail-header\"><div><span class=\"section-kicker\">Project record</span><h3>" + esc(project.title) + "</h3><p>" + esc(project.location) + " · " + progress + "% complete</p></div><button class=\"button button-outline button-small\" type=\"button\" data-action=\"view-portal\">View portal ↗</button></div><div class=\"detail-actions\"><label class=\"select-field\"><span>Stage</span><select data-project-status data-project-id=\"" + esc(project.id) + "\">" + projectStatuses.map(function (status) { return "<option" + (status === project.status ? " selected" : "") + ">" + status + "</option>"; }).join("") + "</select></label></div><div class=\"project-progress\" aria-label=\"Project progress\"><span style=\"width:" + progress + "%\"></span></div><div class=\"admin-section-heading compact\"><div><span class=\"section-kicker\">Delivery rail</span><h4 style=\"margin:0;color:var(--brand-navy);\">Milestones</h4></div><span style=\"color:var(--muted);font-size:.62rem;\">" + milestones.filter(function (item) { return item.complete; }).length + " of " + milestones.length + " complete</span></div><div class=\"milestone-list\">" + milestones.map(function (milestone) { return "<label class=\"milestone-row" + (milestone.complete ? " is-complete" : "") + "\"><input type=\"checkbox\" data-milestone-toggle data-milestone-id=\"" + esc(milestone.id) + "\" data-project-id=\"" + esc(project.id) + "\"" + (milestone.complete ? " checked" : "") + "><span>" + esc(milestone.title) + "</span></label>"; }).join("") + "</div><div class=\"update-editor\"><div class=\"admin-section-heading compact\"><div><span class=\"section-kicker\">Timeline</span><h4 style=\"margin:0;color:var(--brand-navy);\">Add project update</h4></div></div><form data-project-update-form data-project-id=\"" + esc(project.id) + "\"><input name=\"title\" placeholder=\"Update title\" style=\"width:100%;min-height:36px;padding:8px 9px;border:1px solid var(--line);border-radius:3px;font-size:.67rem;margin-bottom:8px;\"><textarea name=\"body\" placeholder=\"What should the client or team know next?\" required></textarea><div class=\"update-editor-footer\"><label><input type=\"checkbox\" name=\"visible\"> Client-visible</label><button type=\"submit\">Add update</button></div></form></div><div class=\"mini-activity\" style=\"margin-top:24px;\">" + (updates.length ? updates.map(function (update) { return "<div class=\"mini-activity-item\"><i></i><div><strong>" + esc(update.title) + "</strong><small>" + esc(update.body) + " · " + esc(update.time) + " · " + (update.visible ? "Client-visible" : "Internal") + "</small></div></div>"; }).join("") : "<p class=\"detail-value\">No updates yet.</p>") + "</div>";
    }

    function renderMedia() {
        var grid = document.querySelector("[data-media-grid]");
        if (!grid) {
            return;
        }
        var projectSelect = document.querySelector("[data-media-project]");
        if (projectSelect) {
            var currentProject = projectSelect.value || mediaProjectFilter;
            projectSelect.innerHTML = "<option value=\"all\">All projects</option>" + state.projects.map(function (project) { return "<option value=\"" + esc(project.id) + "\">" + esc(project.title) + "</option>"; }).join("");
            projectSelect.value = state.projects.some(function (project) { return project.id === currentProject; }) ? currentProject : "all";
            mediaProjectFilter = projectSelect.value;
        }
        var media = state.media.filter(function (item) {
            return (mediaFilter === "all" || item.visibility === mediaFilter) && (mediaProjectFilter === "all" || item.projectId === mediaProjectFilter);
        });
        grid.innerHTML = media.length ? media.map(function (item) {
            var project = byId("projects", item.projectId);
            return "<article class=\"media-item\"><div class=\"media-preview\"><img src=\"" + esc(asset(item.src)) + "\" alt=\"" + esc(item.caption || item.title) + "\"><button type=\"button\" aria-label=\"Preview " + esc(item.title) + "\" data-action=\"lightbox-media\" data-media-id=\"" + esc(item.id) + "\">⌕</button>" + (item.type === "video" ? "<span class=\"project-type\">Video thumbnail</span>" : "") + "</div><div class=\"media-item-body\"><strong>" + esc(item.title) + "</strong><small>" + esc(project ? project.title : "Unassigned") + (item.temporary ? " · Temporary browser preview" : "") + "</small><div class=\"media-controls\"><input type=\"text\" value=\"" + esc(item.caption) + "\" aria-label=\"Caption for " + esc(item.title) + "\" data-media-caption data-media-id=\"" + esc(item.id) + "\"><select aria-label=\"Visibility for " + esc(item.title) + "\" data-media-visibility data-media-id=\"" + esc(item.id) + "\"><option value=\"public\"" + (item.visibility === "public" ? " selected" : "") + ">Public</option><option value=\"client\"" + (item.visibility === "client" ? " selected" : "") + ">Client-only</option><option value=\"internal\"" + (item.visibility === "internal" ? " selected" : "") + ">Internal</option></select></div></div></article>";
        }).join("") : "<div class=\"empty-detail\">No media matches this view.</div>";
    }

    function renderContentEditor() {
        var form = document.querySelector("[data-content-form]");
        if (!form) {
            return;
        }
        var content = state.siteContent;
        form.querySelectorAll("[data-content-field]").forEach(function (field) {
            var key = field.dataset.contentField;
            var value = content[key];
            if (key.indexOf("service-") === 0) {
                var parts = key.split("-");
                var service = (content.services || []).find(function (item) { return item.id === parts[1]; });
                value = service ? service[parts[2]] : "";
            }
            if (value !== undefined) {
                field.value = value;
            }
        });
    }

    function renderAdmin() {
        if (!adminRoot) {
            return;
        }
        renderStats();
        renderPipeline();
        renderOverviewProjects();
        renderActivities();
        renderLeads();
        renderEstimateList();
        renderEstimateEditor();
        renderProjectsList();
        renderProjectEditor();
        renderMedia();
        renderContentEditor();
        applyAdminSection();
    }

    function applyAdminSection() {
        if (!adminRoot) {
            return;
        }
        var titles = { overview: "Overview", leads: "Leads", estimates: "Estimates", projects: "Projects", media: "Media library", content: "Content studio" };
        setText("[data-admin-title]", titles[adminSection] || "Overview");
        adminRoot.querySelectorAll("[data-admin-panel]").forEach(function (panel) {
            panel.classList.toggle("is-active", panel.dataset.adminPanel === adminSection);
        });
        adminRoot.querySelectorAll("[data-admin-nav]").forEach(function (navItem) {
            navItem.classList.toggle("is-current", navItem.dataset.adminNav === adminSection);
        });
    }

    function activateSection(section, pushUrl) {
        if (!adminRoot || ADMIN_SECTIONS.indexOf(section) === -1) {
            return;
        }
        adminSection = section;
        if (pushUrl) {
            var navItem = adminRoot.querySelector("[data-admin-nav='" + section + "']");
            if (navItem) {
                window.history.pushState({ section: section }, "", navItem.href);
            }
        }
        renderAdmin();
        var sidebar = document.querySelector("[data-admin-sidebar]");
        var menu = document.querySelector("[data-admin-menu-toggle]");
        if (sidebar && window.innerWidth <= 860) {
            sidebar.classList.remove("is-open");
            if (menu) {
                menu.setAttribute("aria-expanded", "false");
            }
        }
    }

    function openLeadModal() {
        openModal("<span class=\"section-kicker\">New demo record</span><h2>Add a lead</h2><p>Create a fictional lead to test the owner workflow. Nothing is sent to a server.</p><form data-new-lead-form><label class=\"detail-label\">Name<input name=\"name\" required placeholder=\"Jordan Lee\"></label><label class=\"detail-label\">Service<input name=\"service\" required placeholder=\"Renovations\"></label><label class=\"detail-label\">Location<input name=\"location\" required placeholder=\"Ventura, CA\"></label><label class=\"detail-label\">Email<input name=\"email\" type=\"email\" required placeholder=\"jordan@example.com\"></label><label class=\"detail-label\">Project note<textarea name=\"note\" placeholder=\"What should the team know?\"></textarea></label><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"submit\">Add demo lead</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Cancel</button></div></form>");
    }

    function openNewEstimateModal() {
        var options = state.leads.map(function (lead) { return "<option value=\"" + esc(lead.id) + "\">" + esc(lead.name) + " · " + esc(lead.service) + "</option>"; }).join("");
        openModal("<span class=\"section-kicker\">Scope & pricing</span><h2>Start an estimate</h2><p>Choose a demo lead and create a local estimate workspace with editable line items.</p><form data-new-estimate-form><label class=\"detail-label\">Lead<select name=\"leadId\">" + options + "</select></label><label class=\"detail-label\">Estimate title<input name=\"title\" required value=\"New project estimate\"></label><label class=\"detail-label\">Starting deposit<input name=\"deposit\" type=\"number\" min=\"0\" step=\"100\" value=\"5000\"></label><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"submit\">Create estimate</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Cancel</button></div></form>");
    }

    function openFollowupModal(leadId, schedule) {
        var lead = byId("leads", leadId);
        if (!lead) {
            return;
        }
        openModal("<span class=\"section-kicker\">Lead follow-up</span><h2>" + (schedule ? "Schedule a walkthrough" : "Add a follow-up") + "</h2><p>Keep the next step visible for " + esc(lead.name) + ".</p><form data-followup-form data-lead-id=\"" + esc(lead.id) + "\"><label class=\"detail-label\">Task<input name=\"title\" required value=\"" + (schedule ? "Walkthrough with " + esc(lead.name) : "") + "\" placeholder=\"Call back about scope\"></label><label class=\"detail-label\">Due<input name=\"due\" required value=\"This week\" placeholder=\"Friday\"></label><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"submit\">Save follow-up</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Cancel</button></div></form>");
    }

    function openNewProjectModal() {
        var accepted = state.estimates.filter(function (estimate) {
            return estimate.status === "Accepted" && !state.projects.some(function (project) { return project.estimateId === estimate.id; });
        });
        if (!accepted.length) {
            openModal("<span class=\"section-kicker\">Delivery</span><h2>No accepted estimates yet.</h2><p>Accept an estimate from the Estimates workspace, then convert it into a project here.</p><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"button\" data-action=\"open-section\" data-section=\"estimates\">Review estimates</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Close</button></div>");
            return;
        }
        openModal("<span class=\"section-kicker\">Delivery</span><h2>Create a project</h2><p>Start the delivery timeline from an accepted demo estimate.</p><form data-new-project-form><label class=\"detail-label\">Accepted estimate<select name=\"estimateId\">" + accepted.map(function (estimate) { return "<option value=\"" + esc(estimate.id) + "\">#" + esc(estimate.number) + " · " + esc(estimate.title) + "</option>"; }).join("") + "</select></label><label class=\"detail-label\">Project title<input name=\"title\" required value=\"" + esc(accepted[0].title) + "\"></label><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"submit\">Create project</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Cancel</button></div></form>");
    }

    function openEstimatePreview(estimateId) {
        var estimate = byId("estimates", estimateId);
        if (!estimate) {
            return;
        }
        var total = estimateTotal(estimate.id);
        openModal("<span class=\"section-kicker\">Customer-facing preview · Estimate #" + esc(estimate.number) + "</span><h2>" + esc(estimate.title) + "</h2><p>Prepared for " + esc(estimate.client) + ". This preview demonstrates what a future client could review before acceptance.</p><div class=\"modal-kv\"><span>Scope</span><strong>" + estimateItems(estimate.id).length + " line items</strong></div>" + estimateItems(estimate.id).map(function (item) { return "<div class=\"modal-kv\"><span>" + esc(item.description) + "</span><strong>" + money(item.amount) + "</strong></div>"; }).join("") + "<div class=\"modal-kv\"><span>Project total</span><strong>" + money(total) + "</strong></div><div class=\"modal-kv\"><span>Deposit preview</span><strong>" + money(estimate.deposit) + "</strong></div><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"button\" data-action=\"accept-estimate\" data-estimate-id=\"" + esc(estimate.id) + "\">" + (estimate.status === "Accepted" ? "Accepted" : "Simulate acceptance") + "</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Close preview</button></div>");
    }

    function openMediaLightbox(mediaId) {
        var item = byId("media", mediaId);
        if (!item) {
            return;
        }
        openModal("<span class=\"section-kicker\">" + esc(item.type === "video" ? "Video thumbnail" : "Project media") + "</span><h2>" + esc(item.title) + "</h2><img class=\"modal-image\" src=\"" + esc(asset(item.src)) + "\" alt=\"" + esc(item.caption || item.title) + "\"><p>" + esc(item.caption || "No caption yet.") + "</p><div class=\"modal-actions\"><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Close</button></div>");
    }

    function openStaticLightbox(button) {
        openModal("<span class=\"section-kicker\">Project media</span><h2>" + esc(button.dataset.lightboxAlt || "Project image") + "</h2><img class=\"modal-image\" src=\"" + esc(button.dataset.lightboxSrc) + "\" alt=\"" + esc(button.dataset.lightboxAlt || "Project image") + "\"><div class=\"modal-actions\"><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Close</button></div>");
    }

    function openMessageModal() {
        openModal("<span class=\"section-kicker\">Client portal preview</span><h2>Message the team</h2><p>Keep the project conversation in one place. This demo form shows the interaction without sending email.</p><form data-message-form><label class=\"detail-label\">Subject<input name=\"subject\" required value=\"Question about our project\"></label><label class=\"detail-label\">Message<textarea name=\"message\" rows=\"5\" required placeholder=\"Type a question for Kevin...\"></textarea></label><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"submit\">Send demo message</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Cancel</button></div></form>");
    }

    function createEstimateFromLead(leadId) {
        var lead = byId("leads", leadId);
        if (!lead) {
            return;
        }
        var existing = state.estimates.find(function (estimate) { return estimate.leadId === lead.id; });
        if (existing) {
            selectedEstimateId = existing.id;
            activateSection("estimates", true);
            toast("Estimate #" + existing.number + " opened.");
            return;
        }
        var estimateId = nextId("estimate");
        var estimate = { id: estimateId, number: String(1050 + state.estimates.length), leadId: lead.id, title: lead.service + " scope", client: lead.name, status: "Draft", deposit: 5000, created: "Today" };
        state.estimates.unshift(estimate);
        state.estimateLineItems.push(
            { id: nextId("line"), estimateId: estimateId, description: "Site assessment & preparation", amount: 2500 },
            { id: nextId("line"), estimateId: estimateId, description: "Construction scope", amount: 12000 },
            { id: nextId("line"), estimateId: estimateId, description: "Project coordination", amount: 3500 }
        );
        lead.status = "Quoted";
        selectedEstimateId = estimateId;
        recordActivity("Estimate #" + estimate.number + " created for " + lead.name, lead.service + " · just now");
        saveState();
        activateSection("estimates", true);
        toast("Estimate #" + estimate.number + " created from " + lead.name + ".");
    }

    function createProjectFromEstimate(estimateId, title) {
        var estimate = byId("estimates", estimateId);
        if (!estimate) {
            return;
        }
        var existing = state.projects.find(function (project) { return project.estimateId === estimate.id; });
        if (existing) {
            selectedProjectId = existing.id;
            activateSection("projects", true);
            closeModal();
            toast("Project workspace opened.");
            return;
        }
        var projectId = nextId("project");
        var projectTitle = title || estimate.title;
        var lead = byId("leads", estimate.leadId);
        state.projects.unshift({ id: projectId, estimateId: estimate.id, leadId: estimate.leadId, title: projectTitle, location: lead ? lead.location : "Southern California", status: "Planning", nextStep: "Schedule kickoff", cover: "images/progress-kitchen.png" });
        ["Walkthrough", "Estimate approved", "Selections", "Construction", "Final walkthrough"].forEach(function (milestone, index) {
            state.milestones.push({ id: nextId("milestone"), projectId: projectId, title: milestone, complete: index === 0 || index === 1 });
        });
        state.projectUpdates.unshift({ id: nextId("update"), projectId: projectId, title: "Project workspace created.", body: "The accepted estimate is now ready for kickoff planning.", visible: false, time: "Just now" });
        selectedProjectId = projectId;
        state.portal.projectId = projectId;
        state.portal.estimateId = estimate.id;
        state.portal.paymentStatus = "Not paid yet";
        recordActivity("Project created from estimate #" + estimate.number, projectTitle + " · just now");
        saveState();
        closeModal();
        activateSection("projects", true);
        toast(projectTitle + " is ready for kickoff.");
    }

    function resetDemo() {
        state = clone(seedState);
        selectedLeadId = state.leads[0] ? state.leads[0].id : null;
        selectedEstimateId = state.estimates[0] ? state.estimates[0].id : null;
        selectedProjectId = state.projects[0] ? state.projects[0].id : null;
        mediaFilter = "all";
        mediaProjectFilter = "all";
        saveState();
        renderAdmin();
        renderPortal();
        applySiteContent();
        closeModal();
        toast("Demo data reset to the original seed.");
    }

    function handleAction(action, element) {
        var leadId = element.dataset.leadId;
        var estimateId = element.dataset.estimateId;
        var projectId = element.dataset.projectId;
        if (action === "close-modal") {
            closeModal();
        } else if (action === "reset-demo") {
            openModal("<span class=\"section-kicker\">Demo controls</span><h2>Reset all local demo data?</h2><p>This removes the changes saved in this browser and restores the original seeded leads, estimates, projects, media, and content.</p><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"button\" data-action=\"confirm-reset\">Reset demo data</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Keep my changes</button></div>");
        } else if (action === "confirm-reset") {
            resetDemo();
        } else if (action === "focus-lead") {
            activateSection("leads", true);
        } else if (action === "clear-lead-filters") {
            var searchInput = document.querySelector("[data-lead-search]");
            var filterInput = document.querySelector("[data-lead-filter]");
            if (searchInput) { searchInput.value = ""; }
            if (filterInput) { filterInput.value = "all"; }
            renderLeadList();
            toast("Lead filters cleared.");
        } else if (action === "open-section") {
            closeModal();
            activateSection(element.dataset.section, true);
        } else if (action === "new-lead") {
            openLeadModal();
        } else if (action === "new-estimate") {
            openNewEstimateModal();
        } else if (action === "new-project") {
            openNewProjectModal();
        } else if (action === "toggle-priority") {
            var lead = byId("leads", leadId);
            if (lead) {
                lead.priority = !lead.priority;
                recordActivity((lead.priority ? "Marked " : "Removed priority from ") + lead.name, "Lead pipeline · just now");
                saveState();
                renderAdmin();
                toast(lead.name + (lead.priority ? " marked as priority." : " removed from priority."));
            }
        } else if (action === "convert-lead") {
            createEstimateFromLead(leadId);
        } else if (action === "open-estimate") {
            selectedEstimateId = estimateId;
            activateSection("estimates", true);
        } else if (action === "open-project") {
            selectedProjectId = projectId;
            activateSection("projects", true);
        } else if (action === "add-followup") {
            openFollowupModal(leadId, false);
        } else if (action === "schedule-walkthrough") {
            openFollowupModal(leadId, true);
        } else if (action === "add-line-item") {
            state.estimateLineItems.push({ id: nextId("line"), estimateId: estimateId, description: "New scope item", amount: 0 });
            saveState();
            renderEstimateEditor();
            renderEstimateList();
            toast("Line item added. Edit the description and amount.");
        } else if (action === "remove-line-item") {
            state.estimateLineItems = state.estimateLineItems.filter(function (item) { return item.id !== element.dataset.lineId; });
            saveState();
            renderEstimateEditor();
            renderEstimateList();
            toast("Line item removed.");
        } else if (action === "send-estimate") {
            var toSend = byId("estimates", estimateId);
            if (toSend) {
                toSend.status = "Sent";
                recordActivity("Estimate #" + toSend.number + " sent in demo", toSend.client + " · just now");
                saveState();
                renderAdmin();
                toast("Estimate marked as sent. No email was sent.");
            }
        } else if (action === "preview-estimate") {
            openEstimatePreview(estimateId);
        } else if (action === "accept-estimate") {
            var toAccept = byId("estimates", estimateId);
            if (toAccept) {
                toAccept.status = "Accepted";
                var acceptedLead = byId("leads", toAccept.leadId);
                if (acceptedLead) {
                    acceptedLead.status = "Won";
                }
                recordActivity("Estimate #" + toAccept.number + " accepted in demo", toAccept.client + " · just now");
                saveState();
                closeModal();
                renderAdmin();
                renderPortal();
                toast("Estimate accepted in the demo.");
            }
        } else if (action === "convert-estimate") {
            createProjectFromEstimate(estimateId);
        } else if (action === "view-portal") {
            window.location.href = "/demo/portal/";
        } else if (action === "lightbox-media") {
            openMediaLightbox(element.dataset.mediaId);
        } else if (action === "lightbox-static") {
            openStaticLightbox(element);
        } else if (action === "portal-review-estimate") {
            openEstimatePreview(state.portal.estimateId);
        } else if (action === "portal-pay-deposit") {
            var portalEstimate = byId("estimates", state.portal.estimateId);
            if (!portalEstimate) {
                return;
            }
            if (portalEstimate.status !== "Accepted") {
                openModal("<span class=\"section-kicker\">Deposit preview</span><h2>Review and accept first</h2><p>The demo keeps the same order a real client workflow would use: review the estimate, accept the scope, then mark the deposit as paid.</p><div class=\"modal-actions\"><button class=\"button button-primary\" type=\"button\" data-action=\"portal-review-estimate\">Review estimate</button><button class=\"button button-quiet\" type=\"button\" data-action=\"close-modal\">Close</button></div>");
            } else {
                state.portal.paymentStatus = "Paid";
                recordActivity("Deposit marked paid in demo", portalEstimate.client + " · just now");
                saveState();
                renderPortal();
                toast("Deposit marked paid in the demo. No payment provider was contacted.");
            }
        } else if (action === "portal-message") {
            openMessageModal();
        } else if (action === "portal-show-media") {
            var mediaSection = document.querySelector("#photos");
            if (mediaSection) {
                mediaSection.scrollIntoView({ behavior: "smooth" });
            }
        } else if (action === "admin-menu") {
            var sidebar = document.querySelector("[data-admin-sidebar]");
            if (sidebar) {
                var open = sidebar.classList.toggle("is-open");
                element.setAttribute("aria-expanded", String(open));
            }
        }
    }

    function renderPortal() {
        var portal = document.querySelector(".portal-site");
        if (!portal) {
            return;
        }
        var project = byId("projects", state.portal.projectId) || state.projects[0];
        var estimate = byId("estimates", state.portal.estimateId) || state.estimates[0];
        if (!project || !estimate) {
            return;
        }
        var progress = projectProgress(project.id);
        setText("[data-portal-project-title]", project.title);
        setText("[data-portal-project-status]", project.status);
        var latest = projectUpdates(project.id).filter(function (update) { return update.visible; })[0];
        if (latest) {
            setText("[data-portal-update-title]", latest.title);
            setText("[data-portal-update-body]", latest.body);
            setText(".update-time", "Updated " + latest.time);
        }
        setText("[data-portal-estimate-total]", money(estimateTotal(estimate.id)));
        setText("[data-portal-deposit-amount]", money(estimate.deposit));
        var accepted = estimate.status === "Accepted";
        setText("[data-portal-estimate-status]", accepted ? "Accepted in demo" : "Ready for review");
        setText("[data-portal-estimate-check]", accepted ? "✓" : "•");
        var payLabel = document.querySelector("[data-portal-pay-label]");
        var paymentStatus = document.querySelector("[data-portal-payment-status]");
        var paymentDot = document.querySelector("[data-portal-payment-dot]");
        var payButton = document.querySelector("[data-action='portal-pay-deposit']");
        if (state.portal.paymentStatus === "Paid") {
            if (payLabel) { payLabel.textContent = "Deposit marked paid"; }
            if (paymentStatus) { paymentStatus.textContent = "Paid in demo"; }
            if (paymentDot) { paymentDot.classList.add("is-paid"); }
            if (payButton) { payButton.disabled = true; }
        } else {
            if (payLabel) { payLabel.textContent = accepted ? "Simulate deposit payment" : "Review before deposit"; }
            if (paymentStatus) { paymentStatus.textContent = "Not paid yet"; }
            if (paymentDot) { paymentDot.classList.remove("is-paid"); }
            if (payButton) { payButton.disabled = false; }
        }
        var steps = document.querySelectorAll(".portal-progress-step");
        var milestones = projectMilestones(project.id);
        steps.forEach(function (step, index) {
            var milestone = milestones[index];
            step.classList.toggle("is-complete", Boolean(milestone && milestone.complete));
            step.classList.toggle("is-current", Boolean(milestone && !milestone.complete && !milestones.slice(0, index).some(function (item) { return !item.complete; })));
            if (milestone) {
                var label = step.querySelector("strong");
                var marker = step.querySelector("span");
                if (label) { label.textContent = milestone.title; }
                if (marker) { marker.textContent = milestone.complete ? "✓" : String(index + 1); }
            }
        });
        var mediaGrid = document.querySelector(".portal-media-grid");
        if (mediaGrid) {
            var visibleMedia = state.media.filter(function (item) { return item.projectId === project.id && item.visibility !== "internal"; }).slice(0, 3);
            mediaGrid.innerHTML = visibleMedia.length ? visibleMedia.map(function (item) {
                return "<button class=\"portal-media-tile\" type=\"button\" data-action=\"lightbox-media\" data-media-id=\"" + esc(item.id) + "\"><img src=\"" + esc(asset(item.src)) + "\" alt=\"" + esc(item.caption || item.title) + "\"><span class=\"media-tile-label\">" + esc(item.title) + (item.type === "video" ? " · Video" : "") + "</span></button>";
            }).join("") : "<p class=\"detail-value\">No client-visible media yet.</p>";
        }
    }

    function handleSubmit(event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        if (form.matches("[data-new-lead-form]")) {
            event.preventDefault();
            var newLead = { id: nextId("lead"), name: form.elements.name.value.trim(), service: form.elements.service.value.trim(), location: form.elements.location.value.trim(), email: form.elements.email.value.trim(), phone: "(805) 555-0000", status: "New", priority: false, budget: "To discuss", timeline: "To discuss", source: "Demo entry", note: form.elements.note.value.trim(), followUps: [] };
            state.leads.unshift(newLead);
            selectedLeadId = newLead.id;
            recordActivity("New demo lead added", newLead.name + " · just now");
            saveState();
            closeModal();
            activateSection("leads", false);
            toast(newLead.name + " added to the lead pipeline.");
        } else if (form.matches("[data-new-estimate-form]")) {
            event.preventDefault();
            var leadId = form.elements.leadId.value;
            var lead = byId("leads", leadId);
            var estimateId = nextId("estimate");
            var estimate = { id: estimateId, number: String(1050 + state.estimates.length), leadId: leadId, title: form.elements.title.value.trim(), client: lead ? lead.name : "Demo customer", status: "Draft", deposit: numeric(form.elements.deposit.value), created: "Today" };
            state.estimates.unshift(estimate);
            state.estimateLineItems.push({ id: nextId("line"), estimateId: estimateId, description: "Initial project scope", amount: 0 });
            if (lead) { lead.status = "Quoted"; }
            selectedEstimateId = estimateId;
            recordActivity("Estimate #" + estimate.number + " created", estimate.client + " · just now");
            saveState();
            closeModal();
            activateSection("estimates", false);
            toast("Estimate #" + estimate.number + " created.");
        } else if (form.matches("[data-followup-form]")) {
            event.preventDefault();
            var followLead = byId("leads", form.dataset.leadId);
            if (followLead) {
                followLead.followUps = followLead.followUps || [];
                followLead.followUps.unshift({ id: nextId("followup"), title: form.elements.title.value.trim(), due: form.elements.due.value.trim(), done: false });
                recordActivity("Follow-up added for " + followLead.name, form.elements.title.value.trim() + " · just now");
                saveState();
                closeModal();
                renderAdmin();
                toast("Follow-up saved to " + followLead.name + ".");
            }
        } else if (form.matches("[data-message-form]")) {
            event.preventDefault();
            closeModal();
            toast("Demo message captured locally. No email was sent.");
        } else if (form.matches("[data-project-update-form]")) {
            event.preventDefault();
            var updateProject = byId("projects", form.dataset.projectId);
            if (updateProject) {
                var update = { id: nextId("update"), projectId: updateProject.id, title: form.elements.title.value.trim() || "Project update", body: form.elements.body.value.trim(), visible: form.elements.visible.checked, time: "Just now" };
                state.projectUpdates.unshift(update);
                updateProject.nextStep = update.title;
                recordActivity("Project update added to " + updateProject.title, update.visible ? "Client-visible · just now" : "Internal · just now");
                saveState();
                renderAdmin();
                renderPortal();
                toast(update.visible ? "Client-visible update added." : "Internal update added.");
            }
        } else if (form.matches("[data-content-form]")) {
            event.preventDefault();
            var content = state.siteContent;
            form.querySelectorAll("[data-content-field]").forEach(function (field) {
                var key = field.dataset.contentField;
                if (key.indexOf("service-") === 0) {
                    var parts = key.split("-");
                    var service = (content.services || []).find(function (item) { return item.id === parts[1]; });
                    if (service) {
                        service[parts[2]] = field.value.trim();
                    }
                } else {
                    content[key] = field.value.trim();
                }
            });
            recordActivity("Public content draft saved", "Content studio · just now");
            saveState();
            applySiteContent();
            var indicator = document.querySelector("[data-saved-indicator]");
            if (indicator) {
                indicator.textContent = "Saved locally just now";
            }
            toast("Public preview content saved in this browser.");
        } else if (form.matches("[data-estimate-editor-form]")) {
            event.preventDefault();
            var editEstimate = byId("estimates", form.dataset.estimateId);
            if (editEstimate) {
                editEstimate.client = form.elements.client.value.trim();
                editEstimate.title = form.elements.title.value.trim();
                editEstimate.status = form.elements.status.value;
                editEstimate.deposit = numeric(form.elements.deposit.value);
                var itemRows = Array.prototype.slice.call(form.querySelectorAll("[data-line-amount]")).map(function (amountInput) {
                    var descriptionInput = form.querySelector("[data-line-description][data-line-id='" + amountInput.dataset.lineId + "']");
                    return { id: amountInput.dataset.lineId, estimateId: editEstimate.id, description: descriptionInput ? descriptionInput.value.trim() : "Scope item", amount: numeric(amountInput.value) };
                });
                state.estimateLineItems = state.estimateLineItems.filter(function (item) { return item.estimateId !== editEstimate.id; }).concat(itemRows);
                recordActivity("Estimate #" + editEstimate.number + " updated", editEstimate.title + " · just now");
                saveState();
                renderAdmin();
                toast("Estimate changes saved locally.");
            }
        } else if (form.matches("[data-lead-note-form]")) {
            event.preventDefault();
            var notedLead = byId("leads", form.dataset.leadId);
            var note = form.elements.note.value.trim();
            if (notedLead && note) {
                notedLead.note = note;
                recordActivity("Note added to " + notedLead.name, "Lead record · just now");
                saveState();
                renderAdmin();
                toast("Lead note saved.");
            }
        } else {
            return;
        }
    }

    function handleChange(event) {
        var element = event.target;
        if (element.matches("[data-lead-filter]")) {
            renderLeadList();
        } else if (element.matches("[data-lead-status]")) {
            var lead = byId("leads", element.dataset.leadId);
            if (lead) {
                lead.status = element.value;
                recordActivity(lead.name + " moved to " + lead.status, "Lead pipeline · just now");
                saveState();
                renderAdmin();
                toast("Lead status updated.");
            }
        } else if (element.matches("[data-estimate-status]")) {
            var estimate = byId("estimates", element.closest("[data-estimate-editor-form]").dataset.estimateId);
            if (estimate) {
                estimate.status = element.value;
                saveState();
                renderEstimateList();
                renderEstimateEditor();
                toast("Estimate status changed to " + estimate.status + ".");
            }
        } else if (element.matches("[data-project-status]")) {
            var project = byId("projects", element.dataset.projectId);
            if (project) {
                project.status = element.value;
                recordActivity(project.title + " moved to " + project.status, "Project timeline · just now");
                saveState();
                renderAdmin();
                renderPortal();
                toast("Project stage updated.");
            }
        } else if (element.matches("[data-milestone-toggle]")) {
            var milestone = byId("milestones", element.dataset.milestoneId);
            var milestoneProject = byId("projects", element.dataset.projectId);
            if (milestone && milestoneProject) {
                milestone.complete = element.checked;
                recordActivity(milestoneProject.title + ": " + milestone.title, milestone.complete ? "Milestone complete · just now" : "Milestone reopened · just now");
                saveState();
                renderAdmin();
                renderPortal();
                toast(milestone.complete ? "Milestone marked complete." : "Milestone marked incomplete.");
            }
        } else if (element.matches("[data-media-visibility]")) {
            var media = byId("media", element.dataset.mediaId);
            if (media) {
                media.visibility = element.value;
                recordActivity(media.title + " visibility updated", element.value + " · just now");
                saveState();
                renderMedia();
                renderPortal();
                toast("Media visibility updated.");
            }
        } else if (element.matches("[data-media-caption]")) {
            var captionMedia = byId("media", element.dataset.mediaId);
            if (captionMedia) {
                captionMedia.caption = element.value.trim();
                saveState();
                renderPortal();
                toast("Media caption saved locally.");
            }
        } else if (element.matches("[data-media-project]")) {
            mediaProjectFilter = element.value;
            renderMedia();
        } else if (element.matches("[data-demo-file]")) {
            var fileLabel = element.closest(".file-drop");
            var fileSmall = fileLabel ? fileLabel.querySelector("small") : null;
            if (fileSmall && element.files.length) {
                fileSmall.textContent = element.files.length + " file" + (element.files.length === 1 ? "" : "s") + " selected · Demo only";
            }
        }
    }

    function handleInput(event) {
        var element = event.target;
        if (element.matches("[data-lead-search]")) {
            renderLeadList();
        } else if (element.matches("[data-line-amount], [data-line-description]")) {
            var form = element.closest("[data-estimate-editor-form]");
            if (form) {
                editorTotal(form);
            }
        }
    }

    function handleMediaUpload(event) {
        var files = Array.prototype.slice.call(event.target.files || []);
        if (!files.length) {
            return;
        }
        var projectId = mediaProjectFilter !== "all" ? mediaProjectFilter : selectedProjectId;
        var pending = files.length;
        files.forEach(function (file) {
            if (!file.type || file.type.indexOf("image/") !== 0) {
                pending -= 1;
                return;
            }
            var reader = new FileReader();
            reader.onload = function (loadEvent) {
                state.media.unshift({ id: nextId("media"), projectId: projectId, title: file.name.replace(/\.[^/.]+$/, ""), type: "photo", src: loadEvent.target.result, visibility: "internal", caption: "Temporary browser preview", temporary: true });
                pending -= 1;
                if (pending === 0) {
                    var saved = saveState();
                    renderMedia();
                    renderPortal();
                    toast(saved ? "Demo media added as a temporary browser preview." : "Preview added for this tab; browser storage is full.");
                }
            };
            reader.readAsDataURL(file);
        });
        event.target.value = "";
    }

    function initAdmin() {
        if (!adminRoot) {
            return;
        }
        adminRoot.addEventListener("click", function (event) {
            var nav = event.target.closest("[data-admin-nav]");
            if (nav) {
                event.preventDefault();
                activateSection(nav.dataset.adminNav, true);
                return;
            }
            var mediaFilterButton = event.target.closest("[data-media-filter]");
            if (mediaFilterButton) {
                event.preventDefault();
                adminRoot.querySelectorAll("[data-media-filter]").forEach(function (button) { button.classList.remove("is-selected"); });
                mediaFilterButton.classList.add("is-selected");
                mediaFilter = mediaFilterButton.dataset.mediaFilter;
                renderMedia();
                return;
            }
            var leadRecord = event.target.closest("[data-lead-record]");
            if (leadRecord) {
                selectedLeadId = leadRecord.dataset.leadRecord;
                renderLeads();
                return;
            }
            var estimateRecord = event.target.closest("[data-estimate-record]");
            if (estimateRecord) {
                selectedEstimateId = estimateRecord.dataset.estimateRecord;
                renderEstimateList();
                renderEstimateEditor();
                return;
            }
            var projectRecord = event.target.closest("[data-project-record]");
            if (projectRecord) {
                selectedProjectId = projectRecord.dataset.projectRecord;
                renderProjectsList();
                renderProjectEditor();
                return;
            }
            var actionElement = event.target.closest("[data-action]");
            if (actionElement) {
                event.preventDefault();
                handleAction(actionElement.dataset.action, actionElement);
            }
        });
        var menu = document.querySelector("[data-admin-menu-toggle]");
        if (menu) {
            menu.addEventListener("click", function () { handleAction("admin-menu", menu); });
        }
        document.addEventListener("click", function (event) {
            var staticLightbox = event.target.closest(".js-lightbox");
            if (staticLightbox) {
                event.preventDefault();
                openStaticLightbox(staticLightbox);
            }
        });
        document.addEventListener("input", handleInput);
        document.addEventListener("change", handleChange);
        document.addEventListener("submit", handleSubmit);
        var upload = document.querySelector("[data-media-upload]");
        if (upload) {
            upload.addEventListener("change", handleMediaUpload);
            var dropzone = upload.closest(".upload-button");
            if (dropzone) {
                dropzone.addEventListener("dragover", function (event) {
                    event.preventDefault();
                    dropzone.style.borderColor = "var(--brand-gold)";
                });
                dropzone.addEventListener("dragleave", function () {
                    dropzone.style.borderColor = "";
                });
                dropzone.addEventListener("drop", function (event) {
                    event.preventDefault();
                    dropzone.style.borderColor = "";
                    handleMediaUpload({ target: { files: event.dataTransfer.files, value: "" } });
                });
            }
        }
        window.addEventListener("popstate", function () {
            var path = window.location.pathname.replace(/\/+$/, "");
            var section = path.split("/").pop();
            if (ADMIN_SECTIONS.indexOf(section) !== -1) {
                adminSection = section;
            } else {
                adminSection = "overview";
            }
            renderAdmin();
        });
        renderAdmin();
    }

    function initGlobalModal() {
        var backdrop = document.querySelector("[data-modal]");
        if (!backdrop) {
            return;
        }
        document.addEventListener("click", function (event) {
            var actionElement = event.target.closest("[data-action]");
            if (!actionElement || (adminRoot && adminRoot.contains(actionElement))) {
                return;
            }
            event.preventDefault();
            handleAction(actionElement.dataset.action, actionElement);
        });
        backdrop.addEventListener("click", function (event) {
            if (event.target === backdrop) {
                closeModal();
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeModal();
            }
        });
    }

    initGlobalModal();
    initPublicSite();
    initPublicProjectFilters();
    initAdmin();
    renderPortal();

    window.GCCDemo = {
        getState: function () { return clone(state); },
        reset: resetDemo
    };
}());
