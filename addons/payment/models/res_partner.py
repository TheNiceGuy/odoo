# -*- coding: utf-'8' "-*-"
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from openerp import fields, models


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = 'res.partner'
    payment_method_ids = fields.One2many('payment.method', 'partner_id', 'Payment Methods')
