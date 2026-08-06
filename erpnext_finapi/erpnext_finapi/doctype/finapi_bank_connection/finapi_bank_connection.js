// Copyright (c) 2026, Adomio and contributors
// For license information, please see license.txt

const METHOD =
	"erpnext_finapi.erpnext_finapi.doctype.finapi_bank_connection.finapi_bank_connection.";

frappe.ui.form.on("finAPI Bank Connection", {
	refresh(frm) {
		// Available on an unsaved draft too — the bank search is what fills in the bank
		// id, so hiding it until after the first save is exactly backwards.
		frm.add_custom_button(__("Search Bank"), () => search_bank(frm));

		if (frm.is_new()) {
			frm.set_intro(
				__(
					"1. Pick the finAPI User and hit <b>Search Bank</b> — that fills in the bank id. 2. Save; <b>Import Connection (SCA)</b> then appears and walks you through the TAN."
				),
				"blue"
			);
			return;
		}

		if (!frm.doc.finapi_connection_id) {
			frm.add_custom_button(__("Import Connection (SCA)"), () => start_sca(frm, "start_import"))
				.addClass("btn-primary");
		} else {
			frm.add_custom_button(__("Update Connection (re-consent)"), () =>
				start_sca(frm, "start_update")
			);
			frm.add_custom_button(__("Refresh Accounts"), () => refresh_accounts(frm), __("Setup"));
			frm.add_custom_button(__("Sync Now"), () => sync_now(frm)).addClass("btn-primary");
		}

		show_consent_hint(frm);
	},
});

// --------------------------------------------------------------------------- //
// Bank search
// --------------------------------------------------------------------------- //

function search_bank(frm) {
	if (!frm.doc.finapi_user) {
		frappe.msgprint({
			title: __("finAPI User missing"),
			message: __("Pick a finAPI User first — the bank directory is read with its token."),
			indicator: "orange",
		});
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Search Bank"),
		fields: [
			{
				fieldname: "search",
				fieldtype: "Data",
				label: __("Name, BLZ or BIC"),
				reqd: 1,
				description: __(
					"Name, sort code (BLZ) or BIC. Searching by the BLZ from your IBAN is the surest way — big banks have dozens of near-identical entries."
				),
			},
			{ fieldname: "results", fieldtype: "HTML" },
		],
		primary_action_label: __("Search"),
		primary_action(values) {
			frappe.call({
				method: METHOD + "search_banks",
				args: { search: values.search, finapi_user: frm.doc.finapi_user },
				freeze: true,
				freeze_message: __("Searching finAPI…"),
				callback: (r) => render_banks(frm, dialog, r.message || []),
			});
		},
	});
	dialog.show();
}

function render_banks(frm, dialog, banks) {
	const wrapper = dialog.fields_dict.results.$wrapper.empty();

	if (!banks.length) {
		wrapper.append(`<p class="text-muted">${__("No bank found.")}</p>`);
		return;
	}

	const list = $('<div class="list-group"></div>').appendTo(wrapper);
	banks.forEach((bank) => {
		const interfaces = (bank.interfaces || []).join(", ");
		$(
			`<a href="#" class="list-group-item">
				<b>${frappe.utils.escape_html(bank.name || "")}</b>
				<div class="text-muted small">
					BLZ ${frappe.utils.escape_html(bank.blz || "-")} ·
					BIC ${frappe.utils.escape_html(bank.bic || "-")} ·
					ID ${bank.id} · ${frappe.utils.escape_html(interfaces)}
				</div>
			</a>`
		)
			.appendTo(list)
			.on("click", (e) => {
				e.preventDefault();
				frm.set_value("finapi_bank_id", String(bank.id));
				frm.set_value("bank_name", bank.name);

				// Not every bank offers XS2A — Volksbanken are often FinTS only. Picking an
				// interface the bank does not expose fails later, deep inside the SCA flow.
				const interfaces = bank.interfaces || [];
				if (interfaces.length && !interfaces.includes(frm.doc.interface)) {
					frm.set_value("interface", interfaces[0]);
					frappe.show_alert({
						message: __("Banking interface set to {0} — the only one this bank offers.", [
							interfaces[0],
						]),
						indicator: "blue",
					});
				}

				dialog.hide();
				frappe.show_alert({
					message: __("{0} selected (finAPI id {1}).", [bank.name, bank.id]),
					indicator: "green",
				});
			});
	});
}

// --------------------------------------------------------------------------- //
// SCA wizard
// --------------------------------------------------------------------------- //

function start_sca(frm, method) {
	// The bank declares which credentials it wants — build the form from that.
	frappe.call({
		method: METHOD + "get_login_fields",
		args: {
			finapi_user: frm.doc.finapi_user,
			bank_id: frm.doc.finapi_bank_id,
			interface: frm.doc.interface,
		},
		freeze: true,
		freeze_message: __("Asking the bank which credentials it needs…"),
		callback: (r) => {
			const fields = (r.message || []).map((field, index) => ({
				fieldname: `credential_${index}`,
				fieldtype: field.masked ? "Password" : "Data",
				label: field.label,
				reqd: 1,
			}));

			const dialog = new frappe.ui.Dialog({
				title: __("Bank Login"),
				fields: fields.length
					? fields
					: [
							{
								fieldtype: "HTML",
								options: `<p>${__(
									"This interface needs no credentials — continue to authentication."
								)}</p>`,
							},
						],
				primary_action_label: __("Continue"),
				primary_action(values) {
					const credentials = (r.message || []).map((field, index) => ({
						label: field.label,
						value: values[`credential_${index}`],
					}));
					dialog.hide();
					call_sca(frm, method, { login_credentials: JSON.stringify(credentials) });
				},
			});

			dialog.set_secondary_action_label(__("Cancel"));
			dialog.show();

			// PSD2: make it visible that the PIN only lives on the server for this flow.
			dialog.$wrapper.find(".modal-body").prepend(
				`<div class="alert alert-info small">${__(
					"Credentials are used for this authentication only, are never stored in ERPNext, and are dropped as soon as the flow ends."
				)}</div>`
			);
		},
	});
}

function call_sca(frm, method, args) {
	frappe.call({
		method: METHOD + method,
		args: { connection: frm.doc.name, ...args },
		freeze: true,
		freeze_message: __("Talking to the bank…"),
		callback: (r) => handle_sca_state(frm, r.message || {}),
	});
}

function handle_sca_state(frm, state) {
	switch (state.state) {
		case "completed":
			frappe.show_alert({
				message: __("Connection established — {0} account(s), {1} linked to a Bank Account.", [
					state.accounts,
					state.bank_accounts_linked,
				]),
				indicator: "green",
			});
			frm.reload_doc();
			break;

		case "two_step":
			pick_procedure(frm, state);
			break;

		case "challenge":
			enter_challenge(frm, state);
			break;

		case "redirect":
			frappe.msgprint({
				title: __("Authentication in your banking app"),
				message: `${frappe.utils.escape_html(state.message || "")}<br><br>
					<a href="${state.redirect_url}" target="_blank" class="btn btn-primary btn-sm">
						${__("Open bank")}</a>
					<br><br>${__("Confirm there, then continue.")}`,
				primary_action: {
					label: __("Continue"),
					action() {
						frappe.hide_msgprint();
						call_sca(frm, "submit_sca_step", {});
					},
				},
			});
			break;

		case "decoupled":
			frappe.confirm(
				`${frappe.utils.escape_html(state.message || "")}<br><br>${__(
					"Confirm in your banking app, then click Yes."
				)}`,
				() => call_sca(frm, "submit_sca_step", {})
			);
			break;

		case "cancelled":
			frappe.show_alert({ message: __("Authentication cancelled."), indicator: "orange" });
			break;

		default:
			frappe.msgprint(__("Unexpected authentication state: {0}", [state.state]));
	}
}

function pick_procedure(frm, state) {
	const options = (state.procedures || []).map((procedure) => ({
		label: procedure.procedureName || procedure.procedureChallengeType || procedure.procedureId,
		value: procedure.procedureId,
	}));

	const dialog = new frappe.ui.Dialog({
		title: __("Choose TAN Procedure"),
		fields: [
			{
				fieldname: "procedure",
				fieldtype: "Select",
				label: __("Procedure"),
				options: options.map((o) => ({ label: o.label, value: o.value })),
				default: options.length ? options[0].value : "",
				reqd: 1,
			},
		],
		primary_action_label: __("Continue"),
		primary_action(values) {
			dialog.hide();
			call_sca(frm, "submit_sca_step", { two_step_procedure_id: values.procedure });
		},
	});

	dialog.set_secondary_action_label(__("Cancel"));
	dialog.set_secondary_action(() => {
		dialog.hide();
		call_sca(frm, "cancel_sca", {});
	});
	dialog.show();
}

function enter_challenge(frm, state) {
	const dialog = new frappe.ui.Dialog({
		title: __("Strong Customer Authentication"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-warning">${frappe.utils.escape_html(
					state.message || __("Please enter the TAN.")
				)}</div>`,
			},
			{
				fieldname: "challenge_response",
				fieldtype: "Data",
				label: state.answer_field_label || __("TAN"),
				reqd: 1,
			},
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			dialog.hide();
			call_sca(frm, "submit_sca_step", { challenge_response: values.challenge_response });
		},
	});

	dialog.set_secondary_action_label(__("Cancel"));
	dialog.set_secondary_action(() => {
		dialog.hide();
		call_sca(frm, "cancel_sca", {});
	});
	dialog.show();
}

// --------------------------------------------------------------------------- //
// Accounts & sync
// --------------------------------------------------------------------------- //

function refresh_accounts(frm) {
	frappe.call({
		method: METHOD + "refresh_accounts",
		args: { connection: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const res = r.message || {};
			frappe.show_alert({
				message: __("{0} account(s), {1} linked to a Bank Account.", [
					res.accounts,
					res.bank_accounts_linked,
				]),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function sync_now(frm) {
	frappe.call({
		method: METHOD + "sync_now",
		args: { connection: frm.doc.name },
		freeze: true,
		callback: (r) => frappe.show_alert({ message: r.message, indicator: "blue" }),
	});
}

function show_consent_hint(frm) {
	if (!frm.doc.consent_expiry) return;

	const days = frappe.datetime.get_day_diff(frm.doc.consent_expiry, frappe.datetime.now_datetime());
	if (days <= 0) {
		frm.dashboard.set_headline_alert(
			__("The PSD2 consent has expired — run 'Update Connection' to keep syncing."),
			"red"
		);
	} else if (days <= 14) {
		frm.dashboard.set_headline_alert(
			__("The PSD2 consent expires in {0} day(s).", [Math.round(days)]),
			"orange"
		);
	}
}
