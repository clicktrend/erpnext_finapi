// Copyright (c) 2026, Adomio and contributors
// For license information, please see license.txt

frappe.ui.form.on("finAPI Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method:
					"erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings.test_connection",
				freeze: true,
				freeze_message: __("Contacting finAPI…"),
				callback: (r) => {
					const res = r.message || {};
					if (res.ok) {
						frappe.show_alert({
							message: __("finAPI connection OK ({0})", [res.environment]),
							indicator: "green",
						});
					} else {
						frappe.msgprint({
							title: __("Connection failed"),
							message: frappe.utils.escape_html(res.error || "Unknown error"),
							indicator: "red",
						});
					}
					frm.reload_doc();
				},
			});
		});
	},
});
