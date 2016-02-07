# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


# class MrpProductProduceLine(models.TransientModel):
#     _name="mrp.product.produce.line"
#     _description = "Product Produce Consume lines"
# 
#     product_id = fields.Many2one('product.product', string='Product')
#     product_qty = fields.Float(string='Quantity (in default UoM)', digits=dp.get_precision('Product Unit of Measure'))
#     lot_id = fields.Many2one('stock.production.lot', string='Lot')
#     produce_id = fields.Many2one('mrp.product.produce', string='Produce')


class MrpProductProduce(models.TransientModel):
    _name = "mrp.product.produce"
    _description = "Product Produce"


    @api.model
    def default_get(self, fields):
        """
        """
        res = super(MrpProductProduce, self).default_get(fields)
        if self._context and self._context.get('active_id'):
            production = self.env['mrp.production'].browse(self._context['active_id'])
            if production._check_serial():
                res['product_qty'] = 1.0
            else:
                produce_operations = production.produce_operation_ids.filtered(lambda x: x.production_state != 'done' and x.product_id.id == production.product_id.id)
                if produce_operations:
                    res['product_qty'] = produce_operations[0].qty_done or produce_operations[0].product_qty
            res['product_id'] = production.product_id.id
            res['product_uom_id'] = production.product_uom_id.id
            res['serial'] = production._check_serial()
            lines = []
            for consume in production.active_consume_line_ids:
                lines += [(0, 0, {'product_id': consume.product_id.id,
                               'product_qty': consume.product_qty,
                               'lot_id': consume.lot_id.id})]
            res['consume_line_ids'] = lines
            print res
        return res

    @api.model
    def _get_track(self):
        production = False
        if self._context and self._context.get('active_id'):
            production = self.env['mrp.production'].browse(self._context['active_id'])
        return production and production.product_id.tracking or 'none'

    product_id = fields.Many2one('product.product')
    product_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom_id = fields.Many2one('product.uom', 'Unit of Measure')
    lot_id = fields.Many2one('stock.production.lot', string='Lot')  # Should only be visible when it is consume and produce mode
#    consume_lines = fields.One2many('mrp.product.produce.line', 'produce_id', string='Products Consumed')
    tracking = fields.Selection(related='product_id.tracking', selection=[('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')], default=_get_track)
    serial = fields.Boolean('Serial Tracking')
    consume_line_ids = fields.One2many('mrp.product.produce.line', 'produce_id', 'Consume lines')

    @api.multi
    def do_produce(self):
        production_id = self._context.get('active_id', False)
        assert production_id, "Production Id should be specified in context as a Active ID."
        production = self.env['mrp.production'].browse(production_id) 
        for line in self.consume_line_ids:
            consume = production.active_consume_line_ids.filtered(lambda x: (x.product_id.id == line.product_id.id) and (x.lot_id.id == False)) 
            consume.lot_id = line.lot_id.id
            consume.product_qty = line.product_qty
        production.action_produce(self.product_qty, self.lot_id, self)
        return {}


class MrpProductProduceLine(models.TransientModel):
    _name='mrp.product.produce.line'
    
    produce_id = fields.Many2one('mrp.product.produce')
    product_id = fields.Many2one('product.product', 'Product')
    product_qty = fields.Float('Quantity')
    tracking = fields.Selection(related='product_id.tracking', selection=[('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')])
    lot_id = fields.Many2one('stock.production.lot', 'Lot', required=True)
    
