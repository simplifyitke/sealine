# -*- coding: utf-8 -*-
##############################################################################
#
#    Globalteckz
#    Copyright (C) 2013-Today Globalteckz (http://www.globalteckz.com)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


{
    'name': 'Customer / Supplier statement & customer overdue payment reports',
    'version': '16.0.0.1',
    'website' : 'https://www.globalteckz.com',
    'category': 'Accounts',
    'summary': 'Apps for print customer statement report print vendor statement payment reminder customer payment followup send customer statement print account statement reports print overdue statement reports send overdue statement print supplier statement reports',
    'description': """
customer statement
supplier statement
overdue statement
pending statement
customer follow up
customer overdue statement
customer account statement
supplier account statement
Send customer overdue statements by email
send overdue email
outstanding invoice
customer overdue payments
customer statement
invoice
reminder
monthly
    """,
    'author': 'Globalteckz',
	"price": "59.00",
    "currency": "EUR",
    'images': ['static/description/BANNER.png'],
	"live_test_url" : "http://statement12.erpodoo.in:8069",
    "license" : "Other proprietary",
    'depends': ['sale_management',
                'purchase',
                'account',
                'stock',
                'sale_stock',
                ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_statements.xml',
        'report/acc_statemnt_view.xml',
        'report/email_acc_statement.xml',
        'report/email_overdue.xml',
        'report/report_view.xml',
        'views/partner_view.xml',
        'views/send_mail_view.xml',
        'views/account_move_view.xml'
    ],
    'qweb' : [
    ],
    'demo': [
    ],
    'test': [
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
