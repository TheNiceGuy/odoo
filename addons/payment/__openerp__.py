# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Payment Acquirer',
    'category': 'Hidden',
    'summary': 'Payment Acquirer Base Module',
    'version': '1.0',
    'description': """Payment Acquirer Base Module""",
    'author': 'Odoo S.A',
    'depends': ['account'],
    'data': [
        'views/payment_acquirer.xml',
        'views/res_config_view.xml',
        'views/res_partner_view.xml',
        'security/ir.model.access.csv',
        'security/payment_security.xml',
    ],
    'installable': True,
    'auto_install': True,
}
