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

    @api.one
    @api.depends('order_ids')
    def _compute_orders(self):
        self.nb_orders = self.env['mrp.production.workcenter.line'].search_count([('workcenter_id', '=', self.id), ('state', '!=', 'done')]) #('state', 'in', ['pending', 'startworking'])

    note = fields.Text(string='Description', help="Description of the Work Center. ")
    capacity = fields.Float(string='Capacity', default=1.0, help="Number of work orders this Work Center can do in parallel. If this Work Center represents a team of 5 workers, the capacity is 5.")
    time_start = fields.Float(string='Time before prod.', help="Time in hours for the setup.")
    time_stop = fields.Float(string='Time after prod.', help="Time in hours for the cleaning.")
    resource_id = fields.Many2one('resource.resource', string='Resource', ondelete='cascade', required=True)
    resource_type = fields.Selection([('user', 'Human'), ('material', 'Material')], string='Resource Type', required=True, default='material') #TODO: to be removed
    order_ids = fields.One2many('mrp.production.workcenter.line', 'workcenter_id', string="Orders")
    routing_line_ids = fields.One2many('mrp.routing.workcenter', 'workcenter_id', "Routing Lines")
    nb_orders = fields.Integer('Computed Orders', compute='_compute_orders')
    color = fields.Integer('Color')

    @api.multi
    @api.constrains('capacity')
    def _check_capacity(self):
        for obj in self:
            if obj.capacity <= 0.0:
                raise ValueError(_('The capacity must be strictly positive.'))
