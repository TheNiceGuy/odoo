# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Products & Pricelists',
    'version': '1.1',
    'author': 'OpenERP SA',
    'category': 'Sales Management',
    'depends': ['base', 'decimal_precision', 'mail', 'report'],
    'website': 'https://www.odoo.com',
    'description': """
This is the base module for managing products and pricelists in OpenERP.
========================================================================

Products support variants, different pricing methods, suppliers information,
make to stock/order, different unit of measures, packaging and properties.

Pricelists support:
-------------------
    * Multiple-level of discount (by product, category, quantities)
    * Compute price based on different criteria:
        * Other pricelist
        * Cost price
        * List price
        * Supplier price

Pricelists preferences by product and/or partners.

Print product labels with barcode.
    """,
    'data': [
        'security/product_security.xml',
        'security/ir.model.access.csv',
        'wizard/product_price_view.xml',
        'views/res_config_view.xml',
        'data/product_data.xml',
        'data/product_demo.xml',
        'data/product_image_demo.xml',
        'product_report.xml',
        'views/product_view.xml',
        'views/pricelist_view.xml',
        'views/partner_view.xml',
        'views/report_pricelist.xml',
        'views/report_productlabel.xml'
    ],
    'test': [
        'product_pricelist_demo.yml',
        'test/product_pricelist.yml',
    ],
    'installable': True,
    'auto_install': False,
}
