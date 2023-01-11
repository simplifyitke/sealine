# -*- coding: utf-8 -*-
# Part of Odoo, Aktiv Software PVT. LTD.
# See LICENSE file for full copyright & licensing details.

from odoo import models, fields, api


class Accountmove(models.Model):
    """Account statements."""

    _inherit = "account.move"

    payment_amount = fields.Monetary(
        string="Amount Paid", compute="compute_payment_amount"
    )

    @api.depends("amount_total", "amount_residual")
    def compute_payment_amount(self):
        """Calculate the paid amount of a invoice/bill."""
        for invoice_rec in self:
            invoice_rec.payment_amount = (
                invoice_rec.amount_total - invoice_rec.amount_residual
            )
