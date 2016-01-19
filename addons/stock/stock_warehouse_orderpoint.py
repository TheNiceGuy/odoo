# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
import odoo.addons.decimal_precision as dp
from odoo.exceptions import UserError

class StockWarehouseOrderpoint(models.Model):
    """
    Defines Minimum stock rules.
    """
    _name = "stock.warehouse.orderpoint"
    _description = "Minimum Inventory Rule"

    @api.multi
    def subtract_procurements_from_orderpoints(self):
        '''This function returns quantity of product that needs to be deducted from the orderpoint computed quantity because there's already a procurement created with aim to fulfill it.
        '''

        self.env.cr.execute("""select op.id, p.id, p.product_uom, p.product_qty, pt.uom_id, sm.product_qty from procurement_order as p left join stock_move as sm ON sm.procurement_id = p.id,
                                    stock_warehouse_orderpoint op, product_product pp, product_template pt
                                WHERE p.orderpoint_id = op.id AND p.state not in ('done', 'cancel') AND (sm.state IS NULL OR sm.state not in ('draft'))
                                AND pp.id = p.product_id AND pp.product_tmpl_id = pt.id
                                AND op.id IN %s
                                ORDER BY op.id, p.id
                    """, (tuple(self.ids),))
        results = self.env.cr.fetchall()
        current_proc = False
        current_op = False
        op_qty = 0
        res = dict.fromkeys(self.ids, 0.0)
        for move_result in results:
            op = move_result[0]
            if current_op != op:
                if current_op:
                    res[current_op] = op_qty
                current_op = op
                op_qty = 0
            proc = move_result[1]
            if proc != current_proc:
                op_qty += self.env["product.uom"]._compute_qty(move_result[2], move_result[3], move_result[4], round=False)
                # op_qty += move_result[2]._compute_qty(move_result[3], move_result[4], round=False)
                current_proc = proc
            if move_result[5]:  # If a move is associated (is move qty)
                op_qty -= move_result[5]
        if current_op:
            res[current_op] = op_qty
        return res

    @api.multi
    @api.constrains('product_id', 'product_uom')
    def _check_product_uom(self):
        '''
        Check if the UoM has the same category as the product standard UoM
        '''
        for rule in self:
            if rule.product_id.uom_id.category_id.id != rule.product_uom.category_id.id:
                raise UserError(_('You have to select a product unit of measure in the same category than the default unit of measure of the product'))
        return True

    name = fields.Char(required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('stock.orderpoint') or '')
    active = fields.Boolean(help="If the active field is set to False, it will allow you to hide the orderpoint without removing it.", default=lambda *a: 1)
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse', required=True, ondelete="cascade")
    location_id = fields.Many2one('stock.location', 'Location', required=True, ondelete="cascade")
    product_id = fields.Many2one('product.product', 'Product', required=True, ondelete='cascade', domain=[('type', '=', 'product')])
    product_uom = fields.Many2one(related='product_id.uom_id', relation='product.uom', string='Product Unit of Measure', readonly=True, required=True, default=lambda self: self.env.context.get('product_uom'))
    product_min_qty = fields.Float('Minimum Quantity', required=True,
        digits_compute=dp.get_precision('Product Unit of Measure'),
        help="When the virtual stock goes below the Min Quantity specified for this field, Odoo generates "\
        "a procurement to bring the forecasted quantity to the Max Quantity.")
    product_max_qty = fields.Float('Maximum Quantity', required=True,
        digits_compute=dp.get_precision('Product Unit of Measure'),
        help="When the virtual stock goes below the Min Quantity, Odoo generates "\
        "a procurement to bring the forecasted quantity to the Quantity specified as Max Quantity.")
    qty_multiple = fields.Float('Qty Multiple', required=True,
        digits_compute=dp.get_precision('Product Unit of Measure'),
        help="The procurement quantity will be rounded up to this multiple.  If it is 0, the exact quantity will be used.  ", default=lambda *a: 1)
    procurement_ids = fields.One2many('procurement.order', 'orderpoint_id', 'Created Procurements')
    group_id = fields.Many2one('procurement.group', 'Procurement Group', help="Moves created through this orderpoint will be put in this procurement group. If none is given, the moves generated by procurement rules will be grouped into one big picking.", copy=False)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.user.company_id)
    lead_days = fields.Integer('Lead Time', help="Number of days after the orderpoint is triggered to receive the products or to order to the vendor", default=lambda *a: 1)
    lead_type = fields.Selection([('net', 'Day(s) to get the products'), ('supplier', 'Day(s) to purchase')], 'Lead Type', required=True, default=lambda *a: 'supplier')

    _sql_constraints = [
        ('qty_multiple_check', 'CHECK( qty_multiple >= 0 )', 'Qty Multiple must be greater than or equal to zero.'),
    ]

    @api.model
    def default_get(self, fields):
        StockWarehouse = self.env['stock.warehouse']
        res = super(StockWarehouseOrderpoint, self).default_get(fields)
        # default 'warehouse_id' and 'location_id'
        if 'warehouse_id' not in res:
            warehouse_ids = res.get('company_id') and StockWarehouse.search([('company_id', '=', res['company_id'])], limit=1) or []
            res['warehouse_id'] = warehouse_ids and warehouse_ids.ids[0] or False
        if 'location_id' not in res:
            res['location_id'] = res.get('warehouse_id') and StockWarehouse.browse(res['warehouse_id']).lot_stock_id.id or False
        return res

    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        """ Finds location id for changed warehouse.
        """
        if self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id.id

    @api.multi
    @api.onchange('product_id')
    def onchange_product_id(self):
        """ Finds UoM for changed product.
        """
        if self.product_id:
            d = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
            self.product_uom = self.product_id.uom_id.id
            return {'domain': d}
        return {'domain': {'product_uom': []}}
