async function api(url, method = "GET", body = null) {
    const opts = {
        method,
        headers: {},
    };

    if (body !== null) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }

    const r = await fetch(url, opts);

    let d = {};

    try {
        d = await r.json();
    } catch {
        d = {};
    }

    if (!r.ok) {
        const message = d.error || `Request failed (${r.status})`;
        toast(message, "error");
        throw new Error(message);
    }

    return d;
}


async function apiForm(url, form) {
    const r = await fetch(url, {
        method: "POST",
        body: form,
    });

    let d = {};

    try {
        d = await r.json();
    } catch {
        d = {};
    }

    if (!r.ok) {
        const message = d.error || `Request failed (${r.status})`;
        toast(message, "error");
        throw new Error(message);
    }

    toast("Done");
    return d;
}


async function requireAuth() {
    try {
        const d = await api("/api/auth/me");

        if (!d.user) {
            location = "/";
            throw new Error("not auth");
        }

        window.currentUser = d.user;

        return d.user;
    } catch (e) {
        if (location.pathname !== "/") {
            location = "/";
        }

        throw e;
    }
}


function toast(msg, type = "ok") {
    const t = document.getElementById("toast");

    if (!t) {
        return;
    }

    t.textContent = msg;
    t.className = type;

    clearTimeout(window._toast);

    window._toast = setTimeout(() => {
        t.className = "";
    }, 3000);
}


function escapeHtml(v) {
    return String(v ?? "").replace(
        /[&<>'"]/g,
        (m) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                "'": "&#39;",
                '"': "&quot;",
            })[m],
    );
}


function labelize(k) {
    return k
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
}


function empty(s) {
    return `<div class="empty">${escapeHtml(s)}</div>`;
}


/*
|--------------------------------------------------------------------------
| Generic table renderer
|--------------------------------------------------------------------------
|
| When actions=true, this currently creates student actions:
|
| Edit
| Delete
| Activate / Deactivate
|
*/

function table(rows, cols, actions = false) {
    if (!rows?.length) {
        return empty("No data available.");
    }

    const headerCells = cols
        .map((c) => `<th>${labelize(c)}</th>`)
        .join("");

    const actionHeader = actions ? "<th>Actions</th>" : "";

    const bodyRows = rows
        .map((r) => {
            const cells = cols
                .map((c) => {
                    if (c === "active" || c === "passed") {
                        return `
                            <td>
                                <span class="badge ${r[c] ? "ok" : "danger"}">
                                    ${r[c] ? "Yes" : "No"}
                                </span>
                            </td>
                        `;
                    }

                    return `
                        <td>
                            ${escapeHtml(r[c] ?? "")}
                        </td>
                    `;
                })
                .join("");

            const actionCell = actions
                ? `
                    <td>
                        <div class="action-group">

                            <button
                                type="button"
                                class="btn btn-sm btn-secondary"
                                onclick="editStudent('${escapeHtml(r.id)}')"
                            >
                                Edit
                            </button>

                            <button
                                type="button"
                                class="btn btn-sm btn-danger"
                                onclick="deleteStudent('${escapeHtml(r.id)}')"
                            >
                                Delete
                            </button>

                            <button
                                type="button"
                                class="btn btn-sm btn-secondary"
                                onclick="toggleStudent(
                                    '${escapeHtml(r.id)}',
                                    ${r.active ? 0 : 1}
                                )"
                            >
                                ${r.active ? "Deactivate" : "Activate"}
                            </button>

                        </div>
                    </td>
                `
                : "";

            return `<tr>${cells}${actionCell}</tr>`;
        })
        .join("");

    return `
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        ${headerCells}
                        ${actionHeader}
                    </tr>
                </thead>

                <tbody>
                    ${bodyRows}
                </tbody>
            </table>
        </div>
    `;
}


/*
|--------------------------------------------------------------------------
| Student status
|--------------------------------------------------------------------------
*/

async function toggleStudent(id, active) {
    const action = active ? "activate" : "deactivate";

    const confirmed = window.confirm(
        `Are you sure you want to ${action} this student?`,
    );

    if (!confirmed) {
        return;
    }

    try {
        await api(
            "/api/students/" + encodeURIComponent(id) + "/status",
            "POST",
            {
                active: !!active,
            },
        );

        toast(
            active
                ? "Student activated successfully."
                : "Student deactivated successfully.",
        );

        if (typeof loadStudents === "function") {
            await loadStudents();
        } else {
            location.reload();
        }
    } catch (error) {
        console.error("Student status update failed:", error);
    }
}


/*
|--------------------------------------------------------------------------
| Edit student
|--------------------------------------------------------------------------
*/

async function editStudent(id) {
    try {
        const response = await api(
            "/api/students/" + encodeURIComponent(id),
        );

        const student = response.student;

        if (!student) {
            toast("Student data not found.", "error");
            return;
        }

        const name = window.prompt(
            "Student name:",
            student.name || "",
        );

        if (name === null) {
            return;
        }

        const email = window.prompt(
            "Student email:",
            student.email || "",
        );

        if (email === null) {
            return;
        }

        const studentCode = window.prompt(
            "Student code:",
            student.student_code || "",
        );

        if (studentCode === null) {
            return;
        }

        const password = window.prompt(
            "New password (leave empty to keep current password):",
            "",
        );

        if (password === null) {
            return;
        }

        const payload = {
            name: name.trim(),
            email: email.trim(),
            student_code: studentCode.trim(),
            active: !!student.active,
        };

        if (password.trim()) {
            payload.password = password.trim();
        }

        await api(
            "/api/students/" + encodeURIComponent(id),
            "PUT",
            payload,
        );

        toast("Student updated successfully.");

        if (typeof loadStudents === "function") {
            await loadStudents();
        } else {
            location.reload();
        }
    } catch (error) {
        console.error("Student update failed:", error);
    }
}


/*
|--------------------------------------------------------------------------
| Delete student
|--------------------------------------------------------------------------
*/

async function deleteStudent(id) {
    const confirmed = window.confirm(
        "Are you sure you want to delete this student?\n\n" +
        "This action cannot be undone.",
    );

    if (!confirmed) {
        return;
    }

    try {
        await api(
            "/api/students/" + encodeURIComponent(id),
            "DELETE",
        );

        toast("Student deleted successfully.");

        if (typeof loadStudents === "function") {
            await loadStudents();
        } else {
            location.reload();
        }
    } catch (error) {
        console.error("Student deletion failed:", error);
    }
}


/*
|--------------------------------------------------------------------------
| Logout
|--------------------------------------------------------------------------
*/

if (document.getElementById("logoutBtn")) {
    document.getElementById("logoutBtn").onclick = async () => {
        try {
            await api("/api/auth/logout", "POST");
        } finally {
            location = "/";
        }
    };
}