# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json

from odoo import models, _, fields
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, get_lang

from datetime import timedelta
from collections import defaultdict


class PartnerLedgerCustomHandler(models.AbstractModel):
    _name = 'account.partner.ledger.usd.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Partner Ledger Custom Handler'

    def convert_to_usd(self, amount):
        date = fields.Datetime.today()
        currency = self.env['res.currency'].search([('name', '=', 'USD')])
        amount_after = self.env.user.company_id.currency_id._convert(amount, currency, self.env.user.company_id, date)
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

                totals_by_column_group[column_group_key]['debit'] += partner_values[column_group_key]['debit']
                totals_by_column_group[column_group_key]['credit'] += partner_values[column_group_key]['credit']
                totals_by_column_group[column_group_key]['balance'] += partner_values[column_group_key]['balance']

            lines.append((0, self._get_report_line_partners(options, partner, partner_values)))

        # Report total line.
        lines.append((0, self._get_report_line_total(options, totals_by_column_group)))

        return lines

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        domain = []

        company_ids = [company_opt['id'] for company_opt in options.get('multi_company', self.env.company)]
        exch_code = self.env['res.company'].browse(company_ids).mapped('currency_exchange_journal_id')
        if exch_code:
            domain += ['!', '&', '&', '&', ('credit', '=', 0.0), ('debit', '=', 0.0), ('amount_currency', '!=', 0.0), ('journal_id', 'in', exch_code.ids)]

        options['forced_domain'] = options.get('forced_domain', []) + domain

    def _caret_options_initializer(self):
        """ Specify caret options for navigating from a report line to the associated journal entry or payment """
        return {
            'account.move.line': [{'name': _("View Journal Entry"), 'action': 'caret_option_open_record_form'}],
            'account.payment': [{'name': _("View Payment"), 'action': 'caret_option_open_record_form', 'action_param': 'payment_id'}],
        }

    def _custom_unfold_all_batch_data_generator(self, report, options, lines_to_expand_by_function):
        partner_ids_to_expand = []
        for line_dict in lines_to_expand_by_function.get('_report_expand_unfoldable_line_partner_ledger', []):
            model, model_id = self.env['account.report']._get_model_info_from_id(line_dict['id'])
            if model == 'res.partner':
                partner_ids_to_expand.append(model_id)

        return {
            'initial_balances': self._get_initial_balance_values(partner_ids_to_expand, options) if partner_ids_to_expand else {},

            # load_more_limit cannot be passed to this call, otherwise it won't be applied per partner but on the whole result.
            # We gain perf from batching, but load every result, even if the limit restricts them later.
            'aml_values': self._get_aml_values(options, partner_ids_to_expand) if partner_ids_to_expand else {},
        }

    def action_open_partner(self, options, params):
        dummy, record_id = self.env['account.report']._get_model_info_from_id(params['id'])

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': record_id,
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'current',
        }

    def _query_partners(self, options):
        """ Executes the queries and performs all the computation.
        :return:        A list of tuple (partner, column_group_values) sorted by the table's model _order:
                        - partner is a res.parter record.
                        - column_group_values is a dict(column_group_key, fetched_values), where
                            - column_group_key is a string identifying a column group, like in options['column_groups']
                            - fetched_values is a dictionary containing:
                                - sum:                              {'debit': float, 'credit': float, 'balance': float}
                                - (optional) initial_balance:       {'debit': float, 'credit': float, 'balance': float}
                                - (optional) lines:                 [line_vals_1, line_vals_2, ...]
        """
        def assign_sum(row):
            fields_to_assign = ['balance', 'debit', 'credit']
            if any(not company_currency.is_zero(row[field]) for field in fields_to_assign):
                groupby_partners.setdefault(row['groupby'], defaultdict(lambda: defaultdict(float)))
                for field in fields_to_assign:
                    groupby_partners[row['groupby']][row['column_group_key']][field] += row[field]

        company_currency = self.env.company.currency_id

        # Execute the queries and dispatch the results.
        query, params = self._get_query_sums(options)

        groupby_partners = {}

        self._cr.execute(query, params)
        for res in self._cr.dictfetchall():
            assign_sum(res)

        # Correct the sums per partner, for the lines without partner reconciled with a line having a partner
        query, params = self._get_sums_without_partner(options)

        self._cr.execute(query, params)
        totals = {}
        for total_field in ['debit', 'credit', 'balance']:
            totals[total_field] = {col_group_key: 0 for col_group_key in options['column_groups']}

        for row in self._cr.dictfetchall():
            totals['debit'][row['column_group_key']] += row['debit']
            totals['credit'][row['column_group_key']] += row['credit']
            totals['balance'][row['column_group_key']] += row['balance']

            if row['groupby'] not in groupby_partners:
                continue

            assign_sum(row)

        if None in groupby_partners:
            # Debit/credit are inverted for the unknown partner as the computation is made regarding the balance of the known partner
            for column_group_key in options['column_groups']:
                groupby_partners[None][column_group_key]['debit'] += totals['credit'][column_group_key]
                groupby_partners[None][column_group_key]['credit'] += totals['debit'][column_group_key]
                groupby_partners[None][column_group_key]['balance'] -= totals['balance'][column_group_key]

        # Retrieve the partners to browse.
        # groupby_partners.keys() contains all account ids affected by:
        # - the amls in the current period.
        # - the amls affecting the initial balance.
        if groupby_partners:
            # Note a search is done instead of a browse to preserve the table ordering.
            partners = self.env['res.partner'].with_context(active_test=False).search([('id', 'in', list(groupby_partners.keys()))])
        else:
            partners = []

        # Add 'Partner Unknown' if needed
        if None in groupby_partners.keys():
            partners = [p for p in partners] + [None]

        return [(partner, groupby_partners[partner.id if partner else None]) for partner in partners]

    def _get_query_sums(self, options):
        """ Construct a query retrieving all the aggregated sums to build the report. It includes:
        - sums for all partners.
        - sums for the initial balances.
        :param options:             The report options.
        :return:                    (query, params)
        """
        params = []
        queries = []
        report = self.env.ref('account_reports.partner_ledger_report')

        # Create the currency table.
        ct_query = self.env['res.currency']._get_query_currency_table(options)
        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(column_group_options, 'normal')
            params.append(column_group_key)
            params += where_params
            queries.append(f"""
                SELECT
                    account_move_line.partner_id                                                          AS groupby,
                    %s                                                                                    AS column_group_key,
                    SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                    SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM {tables}
                LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                WHERE {where_clause}
                GROUP BY account_move_line.partner_id
            """)

        return ' UNION ALL '.join(queries), params

    def _get_initial_balance_values(self, partner_ids, options):
        queries = []
        params = []
        report = self.env.ref('account_reports.partner_ledger_report')
        ct_query = self.env['res.currency']._get_query_currency_table(options)
        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            # Get sums for the initial balance.
            # period: [('date' <= options['date_from'] - 1)]
            new_options = self._get_options_initial_balance(column_group_options)
            tables, where_clause, where_params = report._query_get(new_options, 'normal', domain=[('partner_id', 'in', partner_ids)])
            params.append(column_group_key)
            params += where_params
            queries.append(f"""
                SELECT
                    account_move_line.partner_id,
                    %s                                                                                    AS column_group_key,
                    SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                    SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM {tables}
                LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                WHERE {where_clause}
                GROUP BY account_move_line.partner_id
            """)

        self._cr.execute(" UNION ALL ".join(queries), params)

        init_balance_by_col_group = {
            partner_id: {column_group_key: {} for column_group_key in options['column_groups']}
            for partner_id in partner_ids
        }
        for result in self._cr.dictfetchall():
            init_balance_by_col_group[result['partner_id']][result['column_group_key']] = result

        return init_balance_by_col_group

    def _get_options_initial_balance(self, options):
        """ Create options used to compute the initial balances for each partner.
        The resulting dates domain will be:
        [('date' <= options['date_from'] - 1)]
        :param options: The report options.
        :return:        A copy of the options, modified to match the dates to use to get the initial balances.
        """
        new_date_to = fields.Date.from_string(options['date']['date_from']) - timedelta(days=1)
        new_date_options = dict(options['date'], date_from=False, date_to=fields.Date.to_string(new_date_to))
        return dict(options, date=new_date_options)

    def _get_sums_without_partner(self, options):
        """ Get the sum of lines without partner reconciled with a line with a partner, grouped by partner. Those lines
        should be considered as belonging to the partner for the reconciled amount as it may clear some of the partner
        invoice/bill and they have to be accounted in the partner balance."""
        queries = []
        params = []
        report = self.env.ref('account_reports.partner_ledger_report')
        for column_group_key, column_group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(column_group_options, 'normal')
            params += [
                column_group_key,
                column_group_options['date']['date_to'],
                *where_params,
            ]
            queries.append(f"""
                SELECT
                    %s                                                                                                    AS column_group_key,
                    aml_with_partner.partner_id                                                                           AS groupby,
                    COALESCE(SUM(CASE WHEN aml_with_partner.balance > 0 THEN 0 ELSE partial.amount END), 0)               AS debit,
                    COALESCE(SUM(CASE WHEN aml_with_partner.balance < 0 THEN 0 ELSE partial.amount END), 0)               AS credit,
                    COALESCE(SUM(CASE WHEN aml_with_partner.balance > 0 THEN -partial.amount ELSE partial.amount END), 0) AS balance
                FROM {tables}
                JOIN account_partial_reconcile partial
                    ON account_move_line.id = partial.debit_move_id OR account_move_line.id = partial.credit_move_id
                JOIN account_move_line aml_with_partner ON
                    (aml_with_partner.id = partial.debit_move_id OR aml_with_partner.id = partial.credit_move_id)
                    AND aml_with_partner.partner_id IS NOT NULL
                WHERE partial.max_date <= %s AND {where_clause}
                    AND account_move_line.partner_id IS NULL
                GROUP BY aml_with_partner.partner_id
            """)

        return " UNION ALL ".join(queries), params

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
                    amount_usd = convert_initial_balance(amount)
                    return report.format_value(amount_usd, currency=usd_currency,
                                               figure_type='monetary')

                ##NOTE: Do not convert  no_format value otherwise it messes up with calculations
                initial_balance_line['columns'] = [{'name': format_initial_balance(initial_dict.get('no_format')),
                                                    'no_format': initial_dict.get('no_format'),
                                                    'class': 'number'} if initial_dict.get(
                    'class') == 'number' else initial_dict for initial_dict in initial_balance_line['columns']]
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

    def _get_aml_values(self, options, partner_ids, offset=0, limit=None):
        rslt = {partner_id: [] for partner_id in partner_ids}

        partner_ids_wo_none = [x for x in partner_ids if x]
        directly_linked_aml_partner_clauses = []
        directly_linked_aml_partner_params = []
        indirectly_linked_aml_partner_params = []
        indirectly_linked_aml_partner_clause = 'aml_with_partner.partner_id IS NOT NULL'
        if None in partner_ids:
            directly_linked_aml_partner_clauses.append('account_move_line.partner_id IS NULL')
        if partner_ids_wo_none:
            directly_linked_aml_partner_clauses.append('account_move_line.partner_id IN %s')
            directly_linked_aml_partner_params.append(tuple(partner_ids_wo_none))
            indirectly_linked_aml_partner_clause = 'aml_with_partner.partner_id IN %s'
            indirectly_linked_aml_partner_params.append(tuple(partner_ids_wo_none))
        directly_linked_aml_partner_clause = '(' + ' OR '.join(directly_linked_aml_partner_clauses) + ')'

        ct_query = self.env['res.currency']._get_query_currency_table(options)
        queries = []
        all_params = []
        lang = self.env.lang or get_lang(self.env).code
        journal_name = f"COALESCE(journal.name->>'{lang}', journal.name->>'en_US')" if \
            self.pool['account.journal'].name.translate else 'journal.name'
        account_name = f"COALESCE(account.name->>'{lang}', account.name->>'en_US')" if \
            self.pool['account.account'].name.translate else 'account.name'
        report = self.env.ref('account_reports.partner_ledger_report')
        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(group_options, 'strict_range')

            all_params += [
                column_group_key,
                *where_params,
                *directly_linked_aml_partner_params,
                column_group_key,
                *indirectly_linked_aml_partner_params,
                *where_params,
                group_options['date']['date_from'],
                group_options['date']['date_to'],
            ]

            # For the move lines directly linked to this partner
            queries.append(f'''
                SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    account_move_line.partner_id,
                    account_move_line.currency_id,
                    account_move_line.amount_currency,
                    account_move_line.matching_number,
                    ROUND(account_move_line.debit * currency_table.rate, currency_table.precision)   AS debit,
                    ROUND(account_move_line.credit * currency_table.rate, currency_table.precision)  AS credit,
                    ROUND(account_move_line.balance * currency_table.rate, currency_table.precision) AS balance,
                    account_move.name                                                                AS move_name,
                    account_move.move_type                                                           AS move_type,
                    account.code                                                                     AS account_code,
                    {account_name}                                                                   AS account_name,
                    journal.code                                                                     AS journal_code,
                    {journal_name}                                                                   AS journal_name,
                    %s                                                                               AS column_group_key,
                    'directly_linked_aml'                                                            AS key
                FROM {tables}
                JOIN account_move ON account_move.id = account_move_line.move_id
                LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                LEFT JOIN res_company company               ON company.id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN account_account account           ON account.id = account_move_line.account_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                WHERE {where_clause} AND {directly_linked_aml_partner_clause}
                ORDER BY account_move_line.date, account_move_line.id
            ''')

            # For the move lines linked to no partner, but reconciled with this partner. They will appear in grey in the report
            queries.append(f'''
                SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    aml_with_partner.partner_id,
                    account_move_line.currency_id,
                    account_move_line.amount_currency,
                    account_move_line.matching_number,
                    CASE WHEN aml_with_partner.balance > 0 THEN 0 ELSE partial.amount END               AS debit,
                    CASE WHEN aml_with_partner.balance < 0 THEN 0 ELSE partial.amount END               AS credit,
                    CASE WHEN aml_with_partner.balance > 0 THEN -partial.amount ELSE partial.amount END AS balance,
                    account_move.name                                                                   AS move_name,
                    account_move.move_type                                                              AS move_type,
                    account.code                                                                        AS account_code,
                    {account_name}                                                                      AS account_name,
                    journal.code                                                                        AS journal_code,
                    {journal_name}                                                                      AS journal_name,
                    %s                                                                                  AS column_group_key,
                    'indirectly_linked_aml'                                                             AS key
                FROM {tables},
                    account_partial_reconcile partial,
                    account_move,
                    account_move_line aml_with_partner,
                    account_journal journal,
                    account_account account
                WHERE
                    (account_move_line.id = partial.debit_move_id OR account_move_line.id = partial.credit_move_id)
                    AND account_move_line.partner_id IS NULL
                    AND account_move.id = account_move_line.move_id
                    AND (aml_with_partner.id = partial.debit_move_id OR aml_with_partner.id = partial.credit_move_id)
                    AND {indirectly_linked_aml_partner_clause}
                    AND journal.id = account_move_line.journal_id
                    AND account.id = account_move_line.account_id
                    AND {where_clause}
                    AND partial.max_date BETWEEN %s AND %s
                ORDER BY account_move_line.date, account_move_line.id
            ''')

        query = '(' + ') UNION ALL ('.join(queries) + ')'

        if offset:
            query += ' OFFSET %s '
            all_params.append(offset)

        if limit:
            query += ' LIMIT %s '
            all_params.append(limit)

        self._cr.execute(query, all_params)
        for aml_result in self._cr.dictfetchall():
            if aml_result['key'] == 'indirectly_linked_aml':

                # Append the line to the partner found through the reconciliation.
                if aml_result['partner_id'] in rslt:
                    rslt[aml_result['partner_id']].append(aml_result)

                # Balance it with an additional line in the Unknown Partner section but having reversed amounts.
                if None in rslt:
                    rslt[None].append({
                        **aml_result,
                        'debit': aml_result['credit'],
                        'credit': aml_result['debit'],
                        'balance': -aml_result['balance'],
                    })
            else:
                rslt[aml_result['partner_id']].append(aml_result)

        return rslt

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
                # Amount is already converted to USD
                # usd_value = self.convert_to_usd(value)
                formatted_value = report.format_value(value, currency=usd_currency,
                                                      figure_type=column['figure_type'],
                                                      blank_if_zero=column['blank_if_zero'])
            else:
                formatted_value = report.format_value(value, figure_type=column['figure_type']) if value is not None else value

            unfoldable = unfoldable or (col_expr_label in ('debit', 'credit') and not company_currency.is_zero(value))

            column_values.append({
                'name': formatted_value,
                'no_format': value,
                'class': 'number'
            })

        line_id = report._get_generic_line_id('res.partner', partner.id) if partner else report._get_generic_line_id(None, None, markup='no_partner')

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
                col_value = report._format_aml_name(aml_query_result['name'], aml_query_result['ref'], aml_query_result['move_name'])
            else:
                col_value = aml_query_result[col_expr_label] if column['column_group_key'] == aml_query_result['column_group_key'] else None

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
            'id': report._get_generic_line_id('account.move.line', aml_query_result['id'], parent_line_id=partner_line_id),
            'parent_id': partner_line_id,
            'name': format_date(self.env, aml_query_result['date']),
            'class': 'text-muted' if aml_query_result['key'] == 'indirectly_linked_aml' else 'text',  # do not format as date to prevent text centering
            'columns': columns,
            'caret_options': caret_type,
            'level': 2,
        }

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

    def open_journal_items(self, options, params):
        params['view_ref'] = 'account.view_move_line_tree_grouped_partner'
        action = self.env['account.report'].open_journal_items(options=options, params=params)
        action.get('context', {}).update({'search_default_group_by_account': 0, 'search_default_group_by_partner': 1})
        return action
