// Copyright (c) 2026, Adomio and contributors
// For license information, please see license.txt

const METHOD = "erpnext_finapi.erpnext_finapi.doctype.finapi_user.finapi_user.";
const SETTINGS_METHOD =
	"erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings.environment_setup";

frappe.ui.form.on("finAPI User", {
	async onload(frm) {
		// The environment on this record decides which credentials are used, so a new
		// user starts on the one the settings call default instead of on the DocType
		// default (Sandbox) — which used to be the wrong half of every live setup.
		const setup = await environment_setup(frm);
		if (frm.is_new() && setup.default && frm.doc.environment !== setup.default) {
			frm.set_value("environment", setup.default);
		}
	},

	refresh(frm) {
		show_environment_hint(frm);

		if (frm.is_new()) return;

		if (!frm.doc.is_registered) {
			frm.add_custom_button(__("Register at finAPI"), () => {
				frappe.confirm(
					__("Create this user at finAPI? Only do this for a user that does not exist yet."),
					() =>
						frappe.call({
							method: METHOD + "register",
							args: { user: frm.doc.name },
							freeze: true,
							callback: () => frm.reload_doc(),
						})
				);
			});
		}

		// An existing finAPI user usually already owns its connections — adopting them
		// avoids a pointless second SCA consent.
		frm.add_custom_button(__("Discover Bank Connections"), () =>
			frappe.call({
				method: METHOD + "discover_connections",
				args: { user: frm.doc.name },
				freeze: true,
				freeze_message: __("Reading connections from finAPI…"),
				callback: (r) => {
					const res = r.message || {};
					frappe.msgprint({
						title: __("Bank connections"),
						indicator: "green",
						message: __("{0} found · {1} newly created · {2} updated.", [
							res.connections,
							(res.created || []).length,
							(res.updated || []).length,
						]),
					});
				},
			})
		);
	},

	environment(frm) {
		show_environment_hint(frm);
	},
});

// --------------------------------------------------------------------------- //
// Environment
// --------------------------------------------------------------------------- //

async function environment_setup(frm) {
	// Cached on the form: the answer cannot change while the form is open, and the hint
	// below is re-rendered on every refresh.
	if (!frm.__finapi_environment_setup) {
		try {
			const r = await frappe.call({ method: SETTINGS_METHOD });
			frm.__finapi_environment_setup = r.message || {};
		} catch (e) {
			// Never block the form over a hint (no permission on the settings, say).
			frm.__finapi_environment_setup = {};
		}
	}
	return frm.__finapi_environment_setup;
}

async function show_environment_hint(frm) {
	const setup = await environment_setup(frm);
	const configured = setup.configured;
	if (!configured || !frm.doc.environment) return;

	if (configured.includes(frm.doc.environment)) {
		frm.dashboard.clear_headline();
		return;
	}

	// Picking an environment with no client credentials behind it fails much later, at
	// the first call to finAPI — say it here instead.
	frm.dashboard.set_headline_alert(
		configured.length
			? __(
					"finAPI Settings has no {0} credentials — only {1}. Add them, or pick that environment.",
					[frm.doc.environment, configured.join(", ")]
				)
			: __("finAPI Settings has no client credentials yet — configure them before registering."),
		"orange"
	);
}
