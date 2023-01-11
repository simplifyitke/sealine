# -*- coding: utf-8 -*-
# Part of Odoo, Aktiv Software PVT. LTD.
# See LICENSE file for full copyright & licensing details.

from odoo import models, fields, _
from datetime import date
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Find Outstanding invoices for the Selected partner."""

    _inherit = "res.partner"

    customer_invoice_ids = fields.Many2many(
        "account.move",
        "customer_invoice_rel",
        "customer_id",
        "invoice_id",
        string="Customer Statement",
        compute="compute_invoices",
    )
    vendor_bill_ids = fields.Many2many(
        "account.move",
        "vendor_bill_rel",
        "vendor_id",
        "bill_id",
        string="Vendor Statement",
        compute="compute_bills",
    )
    customer_overdue_amount = fields.Monetary(
        string="Total Overdue Amount",
        compute="compute_overdue_and_balance_amount_customer",
    )
    customer_balance_amount = fields.Monetary(
        string="Total Outstanding Balance",
        compute="compute_overdue_and_balance_amount_customer",
    )
    vendor_overdue_amount = fields.Monetary(
        compute="compute_overdue_and_balance_amount_vendor"
    )
    vendor_balance_amount = fields.Monetary(
        compute="compute_overdue_and_balance_amount_vendor"
    )

    def compute_invoices(self):
        """Compute all the invoice of selected customer."""
        invoice_recs = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("partner_id", "=", self.id),
            ]
        )
        self.write(
            {
                "customer_invoice_ids": invoice_recs
                and [(6, 0, invoice_recs.ids)]
                or False
            }
        )

    def compute_bills(self):
        """Compute all the bills of selected Vendor."""
        invoice_recs = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("partner_id", "=", self.id),
            ]
        )
        self.write(
            {"vendor_bill_ids": invoice_recs and [(6, 0, invoice_recs.ids)] or False}
        )

    def compute_overdue_and_balance_amount_customer(self):
        """Compute total overdue amount and total balance amount for vendor."""
        self.customer_overdue_amount = 0
        self.customer_balance_amount = 0
        invoice_recs = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("partner_id", "=", self.id),
            ]
        )
        for invoice_rec in invoice_recs:
            self.customer_balance_amount += invoice_rec.amount_residual
            if invoice_rec.invoice_date_due < date.today():
                self.customer_overdue_amount += invoice_rec.amount_residual

    def compute_overdue_and_balance_amount_vendor(self):
        """Compute total overdue amount and total balance amount for vendor."""
        self.vendor_balance_amount = 0
        self.vendor_overdue_amount = 0
        invoice_recs = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("partner_id", "=", self.id),
            ]
        )
        for invoice_rec in invoice_recs:
            self.vendor_balance_amount += invoice_rec.amount_residual
            if invoice_rec.invoice_date_due < date.today():
                self.vendor_overdue_amount += invoice_rec.amount_residual

    def get_partner_invoice_data(self, invoice_type):
        """Get the common data of partner."""
        data = {}
        search_data = self.env["account.move"].search(
            [
                ("state", "=", "posted"),
                ("partner_id", "=", self.id),
                ("payment_state", "!=", "paid"),
                ("move_type", "=", invoice_type),
            ]
        )

        partner_data = []
        for invoice_rec in search_data:
            vals = {
                "invoice_date": invoice_rec.invoice_date,
                "name": invoice_rec.name,
                "invoice_date_due": invoice_rec.invoice_date_due,
                "amount_total": invoice_rec.amount_total,
                "payment_amount": invoice_rec.payment_amount,
                "amount_residual": invoice_rec.amount_residual,
            }
            partner_data.append(vals)
        data["order"] = partner_data
        return data

    def customer_report(self):
        """Get all the data required for customer report"""
        customer_data = self.get_partner_invoice_data("out_invoice")

        if customer_data.get("order"):
            customer_data["balances"] = {
                "customer_overdue_amount": self.customer_overdue_amount,
                "customer_balance_amount": self.customer_balance_amount,
                "partner_name": self.display_name,
                "partner_type": "customer",
            }
            return self.env.ref(
                "partner_outstanding_info.action_partner_statements_reports"
            ).report_action(self, data=customer_data)
        raise UserError(_("Outstanding data not exist for %s " % self.display_name))

    def vendor_report(self):
        """Get all the data required for vendor report"""
        vendor_data = self.get_partner_invoice_data("in_invoice")

        if vendor_data.get("order"):
            vendor_data["balances"] = {
                "vendor_overdue_amount": self.vendor_overdue_amount,
                "vendor_balance_amount": self.vendor_balance_amount,
                "partner_name": self.display_name,
                "partner_type": "vendor",
            }
            return self.env.ref(
                "partner_outstanding_info.action_partner_statements_reports"
            ).report_action(self, data=vendor_data)
        raise UserError(_("Outstanding data not exist for %s " % self.display_name))
