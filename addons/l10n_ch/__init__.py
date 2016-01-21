# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Author: Nicolas Bessi. Copyright Camptocamp SA
# Financial contributors: Hasa SA, Open Net SA,
#                         Prisme Solutions Informatique SA, Quod SA
# Translation contributors: brain-tec AG, Agile Business Group

from openerp import SUPERUSER_ID

def post_init_func(cr, registry):
    print 'dans le post_init'
    load_translations(cr, registry)
    from openerp.addons.account.models.chart_template import migrate_tags_on_taxes
    migrate_tags_on_taxes(cr, registry)

def load_translations(cr, registry):
    print 'ok in load_translations'
    chart_template = registry['ir.model.data'].xmlid_to_object(cr, SUPERUSER_ID, 'l10n_ch.l10nch_chart_template')
    chart_template.process_coa_translations()
