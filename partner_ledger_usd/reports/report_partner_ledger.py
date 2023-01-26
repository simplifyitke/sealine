# -*- coding: utf-8 -*-
import json
from odoo import api, models, fields, _
from collections import defaultdict
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, get_lang


class MultiReportPartnerLedger(models.AbstractModel):
    _inherit = 'account.partner.ledger.report.handler'

    def convert_to_usd(self, amount):
        date = fields.Datetime.today()
        currency = self.env['res.currency'].search([('name', '=', 'USD')])
        amount_after = self.env.user.company_id.currency_id._convert(amount, currency, self.env.user.company_id, date)
        print("Amount.....................", amount, amount_after)
        return amount_after

    def _get_report_line_total(self, options, totals_by_column_group):
        column_values = []
        report = self.env['account.report']
        for column in options['columns']:
            col_expr_label = column['expression_label']
            value = totals_by_column_group[column['column_group_key']].get(column['expression_label'])

            if col_expr_label in {'debit', 'credit', 'balance'}:
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                ## Value is already converted in USD
                formatted_value = report.format_value(value, currency=usd_currency, figure_type=column['figure_type'],
                                                      blank_if_zero=False)
            else:
                formatted_value = report.format_value(value, figure_type=column['figure_type']) if value else None

            column_values.append({
                'name': formatted_value,
                'no_format': value,
                'class': 'number'
            })

        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('Total'),
            'class': 'total',
            'level': 1,
            'columns': column_values,
        }

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

                totals_by_column_group[column_group_key]['debit'] += self.convert_to_usd(
                    partner_values[column_group_key]['debit'])
                totals_by_column_group[column_group_key]['credit'] += self.convert_to_usd(
                    partner_values[column_group_key]['credit'])
                totals_by_column_group[column_group_key]['balance'] += self.convert_to_usd(
                    partner_values[column_group_key]['balance'])

            lines.append((0, self._get_report_line_partners(options, partner, partner_values)))

        # Report total line.
        lines.append((0, self._get_report_line_total(options, totals_by_column_group)))
        print (lines)
        return lines

    def _report_expand_unfoldable_line_partner_ledger(self, line_dict_id, groupby, options, progress, offset,
                                                      unfold_all_batch_data=None):
        def init_load_more_progress(line_dict):
            return {
                column['column_group_key']: line_col.get('no_format', 0)
                for column, line_col in zip(options['columns'], line_dict['columns'])
                if column['expression_label'] == 'balance'
            }

        report = self.env.ref('account_reports.partner_ledger_report')
        markup, model, record_id = report._parse_line_id(line_dict_id)[-1]

        if markup != 'no_partner' and model != 'res.partner':
            raise UserError(_("Wrong ID for partner ledger line to expand: %s", line_dict_id))

        lines = []

        # Get initial balance
        if offset == 0:
            if unfold_all_batch_data:
                init_balance_by_col_group = unfold_all_batch_data['initial_balances'][record_id]
            else:
                init_balance_by_col_group = self._get_initial_balance_values([record_id], options)[record_id]
            initial_balance_line = report._get_partner_and_general_ledger_initial_balance_line(options, line_dict_id,
                                                                                               init_balance_by_col_group)
            if initial_balance_line:
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                def convert_initial_balance(amount):
                    return self.convert_to_usd(amount)

                def format_initial_balance(amount):
                    amount_usd =  convert_initial_balance(amount)
                    return report.format_value(amount_usd, currency=usd_currency,
                                                      figure_type='monetary')
                ##NOTE: Do not convert  no_format value otherwise it messes up with calculations
                initial_balance_line['columns'] = [{'name': format_initial_balance(initial_dict.get('no_format')),
                                                    'no_format': initial_dict.get('no_format'),'class': 'number'} if initial_dict.get('class') == 'number' else initial_dict for initial_dict in initial_balance_line['columns'] ]
                lines.append(initial_balance_line)

                # For the first expansion of the line, the initial balance line gives the progress
                progress = init_load_more_progress(initial_balance_line)

        limit_to_load = report.load_more_limit + 1 if report.load_more_limit and not self._context.get(
            'print_mode') else None

        if unfold_all_batch_data:
            aml_results = unfold_all_batch_data['aml_values'][record_id]
        else:
            aml_results = self._get_aml_values(options, [record_id], offset=offset, limit=limit_to_load)[record_id]

        has_more = False
        treated_results_count = 0
        next_progress = progress
        for result in aml_results:
            if report.load_more_limit and treated_results_count == report.load_more_limit:
                # We loaded one more than the limit on purpose: this way we know we need a "load more" line
                has_more = True
                break

            new_line = self._get_report_line_move_line(options, result, line_dict_id, next_progress)
            lines.append(new_line)
            next_progress = init_load_more_progress(new_line)
            treated_results_count += 1

        return {
            'lines': lines,
            'offset_increment': treated_results_count,
            'has_more': has_more,
            'progress': json.dumps(next_progress)
        }

    def _get_report_line_move_line(self, options, aml_query_result, partner_line_id, init_bal_by_col_group):
        if aml_query_result['payment_id']:
            caret_type = 'account.payment'
        else:
            caret_type = 'account.move.line'

        columns = []
        report = self.env['account.report']
        for column in options['columns']:
            col_expr_label = column['expression_label']
            if col_expr_label == 'ref':
                col_value = report._format_aml_name(aml_query_result['name'], aml_query_result['ref'],
                                                    aml_query_result['move_name'])
            else:
                col_value = aml_query_result[col_expr_label] if column['column_group_key'] == aml_query_result[
                    'column_group_key'] else None

            if col_value is None:
                columns.append({})
            else:
                col_class = 'number'

                if col_expr_label == 'date_maturity':
                    formatted_value = format_date(self.env, fields.Date.from_string(col_value))
                    col_class = 'date'
                elif col_expr_label == 'amount_currency':
                    usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                    usd_value = self.convert_to_usd(col_value)
                    formatted_value = report.format_value(usd_value, currency=usd_currency,
                                                          figure_type=column['figure_type'])
                elif col_expr_label == 'balance':
                    col_value += init_bal_by_col_group[column['column_group_key']]
                    usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                    usd_value = self.convert_to_usd(col_value)
                    formatted_value = report.format_value(usd_value, currency=usd_currency,
                                                          figure_type=column['figure_type'],
                                                          blank_if_zero=column['blank_if_zero'])
                else:
                    if col_expr_label == 'ref':
                        col_class = 'o_account_report_line_ellipsis'
                    elif col_expr_label not in ('debit', 'credit'):
                        col_class = ''

                    ########## BS #############
                    usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                    usd_value = col_value
                    if isinstance(usd_value, (int, float)):
                        usd_value = self.convert_to_usd(col_value)
                    formatted_value = report.format_value(usd_value, currency=usd_currency,
                                                          figure_type=column['figure_type'])
                    ########## BS #############

                columns.append({
                    'name': formatted_value,
                    'no_format': col_value,
                    'class': col_class,
                })

        return {
            'id': report._get_generic_line_id('account.move.line', aml_query_result['id'],
                                              parent_line_id=partner_line_id),
            'parent_id': partner_line_id,
            'name': format_date(self.env, aml_query_result['date']),
            'class': 'text-muted' if aml_query_result['key'] == 'indirectly_linked_aml' else 'text',
            # do not format as date to prevent text centering
            'columns': columns,
            'caret_options': caret_type,
            'level': 2,
        }

    ####################################################
    # COLUMNS/LINES
    ####################################################
    def _get_report_line_partners(self, options, partner, partner_values):
        company_currency = self.env.company.currency_id
        unfold_all = self._context.get('print_mode') and not options.get('unfolded_lines')

        unfoldable = False
        column_values = []
        report = self.env['account.report']
        for column in options['columns']:
            col_expr_label = column['expression_label']
            value = partner_values[column['column_group_key']].get(col_expr_label)

            if col_expr_label in {'debit', 'credit', 'balance'}:
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')])
                usd_value = self.convert_to_usd(value)
                formatted_value = report.format_value(usd_value, currency=usd_currency,
                                                      figure_type=column['figure_type'],
                                                      blank_if_zero=column['blank_if_zero'])
            else:
                formatted_value = report.format_value(value,
                                                      figure_type=column['figure_type']) if value is not None else value

            unfoldable = unfoldable or (col_expr_label in ('debit', 'credit') and not company_currency.is_zero(value))

            column_values.append({
                'name': formatted_value,
                'no_format': value,
                'class': 'number'
            })

        line_id = report._get_generic_line_id('res.partner', partner.id) if partner else report._get_generic_line_id(
            None, None, markup='no_partner')

        return {
            'id': line_id,
            'name': partner is not None and (partner.name or '')[:128] or _('Unknown Partner'),
            'columns': column_values,
            'level': 2,
            'trust': partner.trust if partner else None,
            'unfoldable': unfoldable,
            'unfolded': line_id in options['unfolded_lines'] or unfold_all,
            'expand_function': '_report_expand_unfoldable_line_partner_ledger',
        }
