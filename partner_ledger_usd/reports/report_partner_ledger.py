# -*- coding: utf-8 -*-

from odoo import api, models, fields
from collections import defaultdict

class MultiReportPartnerLedger(models.AbstractModel):
    _inherit = 'account.partner.ledger.report.handler'

    def convert_to_usd(self, amount):
        date = fields.Datetime.today()
        currency = self.env['res.currency'].search([('name', '=', 'USD')])
        amount_after = self.env.user.company_id.currency_id._convert(amount, currency, self.env.user.company_id, date)
        print("Amount.....................", amount, amount_after)
        return amount_after

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals):
        if self.env.context.get('print_mode') and options.get('filter_search_bar'):
            # Handled here instead of in custom options initializer as init_options functions aren't re-called when printing the report.
            options.setdefault('forced_domain', []).append(('partner_id', 'ilike', options['filter_search_bar']))

        lines = []

        totals_by_column_group = {
            column_group_key: {
                total: 0.0
                for total in ['debit', 'credit', 'balance']
            }
            for column_group_key in options['column_groups']
        }
        for partner, results in self._query_partners(options):
            partner_values = defaultdict(dict)
            for column_group_key in options['column_groups']:
                partner_sum = results.get(column_group_key, {})

                partner_values[column_group_key]['debit'] = self.convert_to_usd(partner_sum.get('debit', 0.0))
                partner_values[column_group_key]['credit'] = self.convert_to_usd(partner_sum.get('credit', 0.0))
                partner_values[column_group_key]['balance'] = self.convert_to_usd(partner_sum.get('balance', 0.0))

                totals_by_column_group[column_group_key]['debit'] += self.convert_to_usd(partner_values[column_group_key]['debit'])
                totals_by_column_group[column_group_key]['credit'] += self.convert_to_usd(partner_values[column_group_key]['credit'])
                totals_by_column_group[column_group_key]['balance'] += self.convert_to_usd(partner_values[column_group_key]['balance'])

            lines.append((0, self._get_report_line_partners(options, partner, partner_values)))

        # Report total line.
        lines.append((0, self._get_report_line_total(options, totals_by_column_group)))

        return lines

    def _custom_line_postprocessor(self, report, options, lines):
        """ Postprocesses the result of the report's _get_lines() before returning it. """
        super(MultiReportPartnerLedger, self)._custom_line_postprocessor(report, options, lines)
        print ("klines...............", lines)
        return lines