# -*- coding: utf-8 -*-
# Part of Odoo, Aktiv Software.
# See LICENSE file for full copyright & licensing details.

# Author: Aktiv Software.
# mail:   odoo@aktivsoftware.com
# Copyright (C) 2015-Present Aktiv Software.
# Contributions:
#           Aktiv Software:
#              - Parth Radadia
#              - Axay Bhuva
#              - Harshil Soni

{
    "name": "Partner Outstanding Payment Information / Statement",
    "summary": """
        This module allows a user to get all the outstanding payment statements
        of partner in partner view.The data will be fetch at Runtime.
        Account,
        Payment,
        Statement,
        Information,
        Outstanding Payment,
        Partner Statement,
        Partner Statement Report,
        Outstanding Report,
        Customer Outstanding,
        Vendor Outstanding,
        Customer Overdue,
        Vendor Overdue,
        Partner Overdue,
        Overdue Report,
        Pending Invoices Report,
        Customer Pending Balance,
        Balance Information,
        Partner Balance,
        Supplier Outstanding,
        Supplier Overdue Report,
        Supplier Report,
        Supplier Statement,
        Supplier Pending Balance,
        OnScreen Statement Information,
        Generate Customer Statement,
        Generate Vendor Statement,
        Get partner pending invoices,
        Get supplier pending invoices,
        Get customer pending invoices,
     """,
    "description": """
        This module allows a user to get all the outstanding payement
        statements of partner in thier form view.Calculate the total
        outstanding amount and total balance of the partner.User can print
        the report of outstanding payment statement.
        Account,
        Payment,
        Statement,
        Information,
        Outstanding Payment,
        Partner Statement,
        Partner Statement Report,
        Outstanding Report,
        Customer Outstanding,
        Vendor Outstanding,
        Customer Overdue,
        Vendor Overdue,
        Partner Overdue,
        Overdue Report,
        Pending Invoices Report,
        Customer Pending Balance,
        Balance Information,
        Partner Balance,
        Supplier Outstanding,
        Supplier Overdue Report,
        Supplier Report,
        Supplier Statement,
        Supplier Pending Balance,
        OnScreen Statement Information,
        Generate Customer Statement,
        Generate Vendor Statement,
        Get partner pending invoices,
        Get supplier pending invoices,
        Get customer pending invoices,
    """,
    "author": "Aktiv Software",
    "website": "http://www.aktivsoftware.com",
    "category": "Account",
    "version": "16.0.1.0.1",
    "depends": ["account"],
    "license": "OPL-1",
    "price": 15.93,
    "currency": "USD",
    "data": [
        "views/res_partner_view.xml",
        "report/report.xml",
        "report/report_template.xml",
    ],
    "images": ["static/description/banner.png"],
}
