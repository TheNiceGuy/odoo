# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Full Reconciliation Concept',
    'version': '1.1',
    'category': 'Accounting & Finance',
    'description': """
Add the concept of full reconciliation back into the accounting.
    """,
    'website': 'https://www.odoo.com/page/accounting',
    'depends': ['account'],
    'data': [
        'views/account_full_reconcile_view.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': True,
}
