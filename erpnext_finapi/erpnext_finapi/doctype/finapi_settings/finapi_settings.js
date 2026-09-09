// Copyright (c) 2026, Adomio and contributors
// For license information, please see license.txt

const METHOD = "erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings.";

frappe.ui.form.on("finAPI Settings", {
	refresh(frm) {
		// No argument: every configured environment is tested. With Sandbox and Live set
		// up side by side, a green light for one says nothing about the other.
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: METHOD + "test_connection",
				freeze: true,
				freeze_message: __("Contacting finAPI…"),
				callback: (r) => {
					const results = (r.message || {}).results || [];
					if ((r.message || {}).ok) {
						frappe.show_alert({
							message: __("finAPI connection OK ({0})", [
								results.map((result) => result.environment).join(", "),
							]),
							indicator: "green",
						});
					} else {
						frappe.msgprint({
							title: __("Connection failed"),
							message: results
								.map((result) =>
									result.ok
										? `<div>${frappe.utils.escape_html(result.environment)}: ${__("OK")}</div>`
										: `<div><b>${frappe.utils.escape_html(
												result.environment
											)}</b>: ${frappe.utils.escape_html(result.error || __("Unknown error"))}</div>`
								)
								.join(""),
							indicator: "red",
						});
					}
					frm.reload_doc();
				},
			});
		});
	},
});
