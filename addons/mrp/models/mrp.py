# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from collections import OrderedDict

import openerp.addons.decimal_precision as dp
from openerp.osv import fields, osv
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT
from openerp.tools import float_compare, float_is_zero
from openerp.tools.translate import _
from openerp import tools, SUPERUSER_ID
from openerp.addons.product import _common
from openerp.exceptions import UserError, AccessError


class mrp_property_group(osv.osv):
    """
    Group of mrp properties.
    """
    _name = 'mrp.property.group'
    _description = 'Property Group'
    _columns = {
        'name': fields.char('Property Group', required=True),
        'description': fields.text('Description'),
    }

class mrp_property(osv.osv):
    """
    Properties of mrp.
    """
    _name = 'mrp.property'
    _description = 'Property'
    _columns = {
        'name': fields.char('Name', required=True),
        'composition': fields.selection([('min','min'),('max','max'),('plus','plus')], 'Properties composition', required=True, help="Not used in computations, for information purpose only."),
        'group_id': fields.many2one('mrp.property.group', 'Property Group', required=True),
        'description': fields.text('Description'),
    }
    _defaults = {
        'composition': lambda *a: 'min',
    }
