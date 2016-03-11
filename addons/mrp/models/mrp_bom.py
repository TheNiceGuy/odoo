# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import openerp.addons.decimal_precision as dp
from openerp import api, fields, models
from openerp.tools.translate import _
from openerp.exceptions import UserError
from openerp.tools import float_round


class MrpBom(models.Model):
    """
    Defines bills of material for a product.
    """
    _name = 'mrp.bom'
    _description = 'Bill of Material'
    _inherit = ['mail.thread']
    _name_rec = 'product_tmpl_id'
    _order = "sequence"

    def _get_uom_id(self):
        return self.env['product.uom'].search([], limit=1, order='id')

    code = fields.Char(string='Reference')
    active = fields.Boolean(string='Active', default=True, help="If the active field is set to False, it will allow you to hide the bills of material without removing it.")
    bom_type = fields.Selection([('normal', 'Manufacture this product'), ('phantom', 'Ship this product as a set of components (kit)')], string='BoM Type', required=True, default='normal',
                                help="Set: When processing a sales order for this product, the delivery order will contain the raw materials, instead of the finished product.", oldname='type')
    product_tmpl_id = fields.Many2one('product.template', string='Product', domain="[('type', 'in', ['product', 'consu'])]", required=True)
    product_id = fields.Many2one('product.product', string='Product Variant',
                                 domain="['&', ('product_tmpl_id','=',product_tmpl_id), ('type','in', ['product', 'consu'])]",
                                 help="If a product variant is defined the BOM is available only for this product.")
    bom_line_ids = fields.One2many('mrp.bom.line', 'bom_id', string='BoM Lines', copy=True)
    categ_id = fields.Many2one('product.category', related='product_tmpl_id.categ_id', string='Product Category', readonly=True, store=True)
    product_qty = fields.Float(string='Quantity', required=True, default=1.0, digits=dp.get_precision('Product Unit of Measure'))
    product_uom_id = fields.Many2one('product.uom', default=_get_uom_id, string='Unit of Measure', required=True, help="Unit of Measure (Unit of Measure) is the unit of measurement for the inventory control", oldname='product_uom')
    sequence = fields.Integer(string='Sequence', help="Gives The sequence order when displaying a list of bills of material.")
    routing_id = fields.Many2one('mrp.routing', string='Routing', help="The list of operations (list of work centers) to produce the finished product. "
                                 "The routing is mainly used to compute work center costs during operations and to plan future loads on work centers based on production planning.")
    ready_to_produce = fields.Selection([('all_available', 'All components available'), ('asap', 'The components of 1st operation')], string='Ready when are available', required=True, default='asap',)
    picking_type_id = fields.Many2one('stock.picking.type', string='Picking Type', domain=[('code', '=', 'mrp_operation')], help="When a procurement has a ‘produce’ route with a picking type set, it will try to create a Manufacturing Order for that product using a BOM of the same picking type. That allows to define pull rules for products with different routing (different BOMs)")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env['res.company']._company_default_get('mrp.bom'))
    operation_id = fields.Many2one('mrp.routing.workcenter', string='Produced at Operation')

    @api.model
    def _bom_find(self, product_tmpl=None, product=None, picking_type=None):
        """ Finds BoM for particular product and product uom.
        :param product_tmpl_id: Selected product.
        :param product_uom_id: Unit of measure of a product.
        :return: False or BoM id.
        """
        if product:
            if not product_tmpl:
                product_tmpl = product.product_tmpl_id
            domain = ['|', ('product_id', '=', product.id), '&', ('product_id', '=', False), ('product_tmpl_id', '=', product_tmpl.id)]
        elif product_tmpl:
            domain = [('product_tmpl_id', '=', product_tmpl.id)]
        else:
            # neither product nor template, makes no sense to search
            return False
        if picking_type:
            domain += ['|', ('picking_type_id', '=', picking_type.id), ('picking_type_id', '=', False)]
        if self.env.context.get('company_id'):
            domain = domain + [('company_id', '=', self.env.context['company_id'])]
        # order to prioritize bom with product_id over the one without
        return self.search(domain, order='sequence, product_id', limit=1)

    # Quantity must be in same UoM than the BoM: convert uom before explode()
    def explode(self, product, quantity, method=None, method_wo=None, done=None):
        self.ensure_one()
        if method_wo and self.routing_id: method_wo(self, quantity)
        done = done or []
        for bom_line in self.bom_line_ids:
            if bom_line._skip_bom_line(product):
                continue
            if bom_line.product_id.product_tmpl_id.id in done:
                raise UserError(_('BoM "%s" contains a BoM line with a product recursion: "%s".') % (self.display_name, bom_line.product_id.display_name))

            # This is very slow, can we improve that?
            bom = self._bom_find(product=bom_line.product_id, picking_type=self.picking_type_id)
            if not bom or bom.bom_type != "phantom":
                quantity = bom_line.product_uom_id._compute_qty(quantity / self.product_qty * bom_line.product_qty, bom.product_uom_id.id)
                if method: method(bom_line, quantity)
            else:
                done.append(self.product_tmpl_id.id)
                # We need to convert to units/UoM of chosen BoM
                qty2 = bom_line.product_uom_id._compute_qty(quantity / self.product_qty * bom_line.product_qty, bom.product_uom_id.id)
                bom.explode(bom_line.product_id, qty2, method=method, method_wo=method_wo, done=done)
        return True

    def _prepare_wc_line(self, wc_use, level=0, factor=1):
        wc = wc_use.workcenter_id
        d, m = divmod(factor, wc_use.workcenter_id.capacity)
        mult = (d + (m and 1.0 or 0.0))
        return {
            'name': ("%s-  %s") % (wc_use.name, self.product_tmpl_id.display_name),
            'workcenter_id': wc.id,
            'sequence': level + (wc_use.sequence or 0),
            'operation_id': wc_use.id,
            'hour': float((wc_use.time_cycle or 0.0) * (wc.time_efficiency or 1.0)),  # + cycle * (wc.time_cycle or 0.0)) * (wc.time_efficiency or 1.0)),
        }

    def _prepare_consume_line(self, bom_line, quantity):
        return {
            'name': bom_line.product_id.name,
            'product_id': bom_line.product_id.id,
            'product_uom_qty': quantity,
            'product_uom_id': bom_line.product_uom_id.id,
            'operation_id': bom_line.operation_id.id,
        }

    def explode_data(self, product, factor, level=0, routing_id=False, previous_products=None, master_bom=None):
        """ Finds Products and Work Centers for related BoM for manufacturing order.
        :param product: Select a particular variant of the BoM. If False use BoM without variants.
        :param factor: Factor represents the quantity, but in UoM of the BoM, taking into account the numbers produced by the BoM
        :param properties: A List of properties.
        :param level: Depth level to find BoM lines starts from 10.
        :param previous_products: List of product previously use by bom explore to avoid recursion
        :param master_bom: When recursion, used to display the name of the master bom
        :return: result: List of dictionaries containing product details.
                 result2: List of dictionaries containing Work Center details.
        """
        master_bom = master_bom or self
        factor = self.product_uom_id._compute_qty(self.product_qty, master_bom.product_uom_id.id)
        result = []
        result2 = []
        routing = (routing_id and self.env['mrp.routing'].browse(routing_id)) or self.routing_id or False
        if routing:
            for wc_use in routing.work_order_ids:
                result2.append(self._prepare_wc_line(wc_use, level=level, factor=factor))
        for bom_line in self.bom_line_ids:
            if bom_line._skip_bom_line(product):
                continue
            if previous_products and bom_line.product_id.product_tmpl_id.id in previous_products:
                raise UserError(_('BoM "%s" contains a BoM line with a product recursion: "%s".') % (master_bom.name, bom_line.product_id.display_name))

            quantity = bom_line.product_uom_id._compute_qty(master_bom.product_qty * bom_line.product_qty, bom_line.product_uom_id.id)
            bom = self._bom_find(product=product)
            # If BoM should not behave like kit, just add the product, otherwise explode further
            if not bom or bom.bom_type != "phantom":
                result.append(self._prepare_consume_line(bom_line, quantity))
            else:
                all_product = [self.product_tmpl_id.id] + (previous_products or [])
                # We need to convert to units/UoM of chosen BoM
                quantity2 = bom_line.product_uom_id._compute_qty(quantity / self.product_qty * bom_line.product_qty, bom.product_uom_id.id)
                res = bom.explode_data(bom_line.product_id, quantity2, level=level + 10, previous_products=all_product, master_bom=master_bom)
                result = result + res[0]
                result2 = result2 + res[1]
        return result, result2

    @api.multi
    def copy_data(self, default=None):
        if default is None:
            default = {}
        return super(MrpBom, self).copy_data(default)[0]

    @api.onchange('product_uom_id')
    def onchange_uom(self):
        res = {}
        if not self.product_uom_id or not self.product_tmpl_id:
            return
        if self.product_uom_id.category_id.id != self.product_tmpl_id.uom_id.category_id.id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
            res['warning'] = {'title': _('Warning'), 'message': _('The Product Unit of Measure you chose has a different category than in the product form.')}
        return res

    @api.multi
    def unlink(self):
        if self.env['mrp.production'].search([('bom_id', 'in', self.ids), ('state', 'not in', ['done', 'cancel'])]):
            raise UserError(_('You can not delete a Bill of Material with running manufacturing orders.\nPlease close or cancel it first.'))
        return super(MrpBom, self).unlink()

    @api.onchange('product_tmpl_id', 'product_qty')
    def onchange_product_tmpl_id(self):
        if self.product_tmpl_id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id

    def name_get(self, cr, uid, ids, context=None):
        res = []
        for record in self.browse(cr, uid, ids, context=context):
            name = record.product_tmpl_id.display_name
            if record.code:
                name = '%s: %s' % (name, record.code)
            res.append((record.id, name))
        return res


class MrpBomLine(models.Model):
    _name = 'mrp.bom.line'
    _order = "sequence"
    _rec_name = "product_id"

    def _get_uom_id(self):
        return self.env['product.uom'].search([], limit=1, order='id')

    # TODO: remove this and reimplement the report in a better way
    @api.multi
    def _get_child_bom_lines(self):
        """If the BOM line refers to a BOM, return the ids of the child BOM lines"""
        for bom_line in self:
            child_bom = self.env['mrp.bom']._bom_find(
                product_tmpl=bom_line.product_id.product_tmpl_id,
                product=bom_line.product_id,
                picking_type=bom_line.bom_id.picking_type_id)
            if child_bom:
                bom_line.child_line_ids = [(6, 0, [bom.id for bom in child_bom.bom_line_ids])]
            else:
                bom_line.child_line_ids = False

    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_qty = fields.Float(string='Product Quantity', required=True, default=1.0, digits=dp.get_precision('Product Unit of Measure'))
    product_uom_id = fields.Many2one('product.uom', string='Product Unit of Measure', required=True, default=_get_uom_id,
                                     help="Unit of Measure (Unit of Measure) is the unit of measurement for the inventory control", oldname='product_uom')
    sequence = fields.Integer(default=1, help="Gives the sequence order when displaying.")
    routing_id = fields.Many2one('mrp.routing', string='Routing',
                                 related="bom_id.routing_id", store=True,
                                 help="The list of operations (list of work centers) to produce the finished product. The routing is mainly used to compute work center costs during operations and to plan future loads on work centers based on production planning.")
    bom_id = fields.Many2one('mrp.bom', string='Parent BoM', ondelete='cascade', index=True, required=True)
    attribute_value_ids = fields.Many2many('product.attribute.value', string='Variants', help="BOM Product Variants needed form apply this line.")
    operation_id = fields.Many2one('mrp.routing.workcenter', string='Consumed in Operation', help="The operation where the components are consumed, or the finished products created.")
    child_line_ids = fields.One2many('mrp.bom.line', compute='_get_child_bom_lines', string='BOM lines of the referred bom')

    procure_method = fields.Selection(selection=[('make_to_stock', 'From Stock'), ('make_to_order', 'Make to Order')], string='Supply Method', required=True, default='make_to_stock',
        help="""By default, the system will take from the stock in the source location and passively wait for availability. The other possibility allows you to directly create a procurement on the source location (and thus ignore its current stock) to gather products. If we want to chain moves and have this one to wait for the previous, this second option should be chosen.""")

    _sql_constraints = [
        ('bom_qty_zero', 'CHECK (product_qty>0)', 'All product quantities must be greater than 0.\n'
            'You should install the mrp_byproduct module if you want to manage extra products on BoMs !'),
    ]

    def _skip_bom_line(self, product):
        """ Control if a BoM line should be produce, can be inherited for add
        custom control.
        :param product: Selected product produced.
        :return: True or False
        """
        # all bom_line_id variant values must be in the product
        if self.attribute_value_ids:
            if not product or self.attribute_value_ids - product.attribute_value_ids:
                return True
        return False

    @api.model
    def create(self, values):
        if 'product_id' in values and 'product_uom_id' not in values:
            values['product_uom_id'] = self.env['product.product'].browse(values.get('product_id')).uom_id.id
        return super(MrpBomLine, self).create(values)

    @api.onchange('product_uom_id')
    def onchange_uom(self):
        res = {}
        if not self.product_uom_id or not self.product_id:
            return
        if self.product_uom_id.category_id.id != self.product_id.uom_id.category_id.id:
            self.product_uom_id = self.product_id.uom_id.id
            res['warning'] = {'title': _('Warning'), 'message': _('The Product Unit of Measure you chose has a different category than in the product form.')}
        return res

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id
