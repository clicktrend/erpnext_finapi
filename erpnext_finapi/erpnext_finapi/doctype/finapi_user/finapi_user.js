// Copyright (c) 2026, Adomio and contributors
// For license information, please see license.txt

const METHOD = "erpnext_finapi.erpnext_finapi.doctype.finapi_user.finapi_user.";

frappe.ui.form.on("finAPI User", {
	refresh(frm) {
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
});
