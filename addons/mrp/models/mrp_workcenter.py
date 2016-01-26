# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _

# ----------------------------------------------------------
# Work Centers
# ----------------------------------------------------------
# capacity_hour : capacity per hour. default: 1.0.
#          Eg: If 5 concurrent operations at one time: capacity = 5 (because 5 employees)


class MrpWorkcenter(models.Model):
    _name = 'mrp.workcenter'
    _description = 'Work Center'
    _inherits = {'resource.resource': "resource_id"}

    @api.depends('order_ids')
    def _compute_orders(self):
        WorkcenterLine = self.env['mrp.production.workcenter.line']
        for workcenter in self:
            workcenter.nb_orders = WorkcenterLine.search_count([('workcenter_id', '=', workcenter.id), ('state', '!=', 'done')]) #('state', 'in', ['pending', 'startworking'])
            workcenter.count_ready_order = WorkcenterLine.search_count([('workcenter_id', '=', workcenter.id), ('state', '=', 'ready')])
            workcenter.count_progress_order = WorkcenterLine.search_count([('workcenter_id', '=', workcenter.id), ('state', '=', 'progress')])

    def _compute_status(self):
        for workcenter in self:
            if workcenter.count_progress_order:
                workcenter.status = 'done'
            else:
                workcenter.status = 'normal'

    note = fields.Text(string='Description', help="Description of the Work Center. ")
    capacity = fields.Float(string='Capacity', default=1.0, help="Number of work orders this Work Center can do in parallel. If this Work Center represents a team of 5 workers, the capacity is 5.")
    time_start = fields.Float(string='Time before prod.', help="Time in hours for the setup.")
    sequence = fields.Integer(required=True, default=1, help="Gives the sequence order when displaying a list of work centers.")
    time_stop = fields.Float(string='Time after prod.', help="Time in hours for the cleaning.")
    resource_id = fields.Many2one('resource.resource', string='Resource', ondelete='cascade', required=True)
    order_ids = fields.One2many('mrp.production.workcenter.line', 'workcenter_id', string="Orders")
    routing_line_ids = fields.One2many('mrp.routing.workcenter', 'workcenter_id', "Routing Lines")
    nb_orders = fields.Integer('Computed Orders', compute='_compute_orders')
    color = fields.Integer('Color')
    count_ready_order = fields.Integer(compute='_compute_orders', string="Total Ready Orders")
    count_progress_order = fields.Integer(compute='_compute_orders', string="Total Running Orders")
    status = fields.Selection([('normal', 'Work order is not running'), ('blocked', 'Work center is block'), ('done', 'Work order is running')],
                                    string='Status', compute="_compute_status")

    @api.multi
    @api.constrains('capacity')
    def _check_capacity(self):
        for obj in self:
            if obj.capacity <= 0.0:
                raise ValueError(_('The capacity must be strictly positive.'))
            

class MrpWorkOrderConsume(models.Model):

    _name = 'mrp.production.workcenter.line.consume'
    
    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
    product_id = fields.Many2one('product.product', 'Product')
    product_qty = fields.Float('Quantity')
    lot_id = fields.Many2one('stock.production.lot', 'Lot')
    #sequence = fields.Integer('Sequence')
    processed = fields.Boolean('Processed', default=False)
    final_lot_id = fields.Many2one('stock.production.lot', 'Final Lot')
    final_qty = fields.Float('Quantity')
    