# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _


class MrpRouting(models.Model):
    """ Specifies routings of work centers """
    _name = 'mrp.routing'
    _description = 'Routings'

    name = fields.Char('Routing Name', required=True)
    active = fields.Boolean(
        'Active', default=True,
        help="If the active field is set to False, it will allow you to hide the routing without removing it.")
    code = fields.Char(
        'Reference',
        copy=False, default=lambda self: _('New'), readonly=True)
    note = fields.Text('Description')
    workorder_ids = fields.One2many(
        'mrp.routing.workcenter', 'routing_id', 'Work Center Usage',
        copy=True, oldname='workcenter_lines')
    location_id = fields.Many2one(
        'stock.location', 'Production Location',
        help="Keep empty if you produce at the location where the finished products are needed."
             "Set a location if you produce at a fixed location. This can be a partner location "
             "if you subcontract the manufacturing operations.")
    company_id = fields.Many2one(
        'res.company', 'Company',
        default=lambda self: self.env['res.company']._company_default_get('mrp.routing'))

    @api.model
    def create(self, vals):
        # TDE CLEANME: strange
        if 'code' not in vals or vals['code'] == _('New'):
            vals['code'] = self.env['ir.sequence'].next_by_code('mrp.routing') or '/'
        return super(MrpRouting, self).create(vals)


class MrpRoutingWorkcenter(models.Model):
    _name = 'mrp.routing.workcenter'
    _description = 'Work Center Usage'
    _order = 'sequence, id'

    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True)
    name = fields.Char('Operation', required=True)
    sequence = fields.Integer(
        'Sequence', default=100,
        help="Gives the sequence order when displaying a list of routing Work Centers.")
    routing_id = fields.Many2one(
        'mrp.routing', 'Parent Routing',
        index=True, ondelete='cascade', required=True,
        help="Routings indicates all the Work Centers used and for how long. "
             "If Routings is indicated then,the third tab of a production order "
             "(Work Centers) will be automatically pre-completed.")
    note = fields.Text('Description')
    company_id = fields.Many2one(
        'res.company', 'Company',
        readonly=True, related='routing_id.company_id', store=True)
    worksheet = fields.Binary('worksheet')
    time_mode = fields.Selection([
        ('auto', 'Compute based on real time'),
        ('manual', 'Set duration manually')], string='Duration Computation',
        default='auto')
    time_mode_batch = fields.Integer('Based on', default=10)
    time_cycle_manual = fields.Float(
        'Manual Duration', default=60,
        help="Time in minutes")
    time_cycle = fields.Float('Duration', compute="_get_time_cycle")
    # TDE CHECKME: be coherent in naming
    wo_count = fields.Integer("# of Work Orders", compute="_wo_count")
    batch = fields.Selection([
        ('no',  'Once all products are processed'),
        ('yes', 'Once a minimum number of products is processed')], string='Next Operation',
        default='no', required=True)
    batch_size = fields.Float('Quantity to Process', default=1.0)

    @api.multi
    def _get_time_cycle(self):
        manual_ops = self.filtered(lambda operation: operation.time_mode == 'manual')
        for operation in manual_ops:
            operation.time_cycle = operation.time_cycle_manual
        for operation in self - manual_ops:
            data = self.env['mrp.workorder'].read_group([
                ('operation_id', '=', operation.id),
                ('state', '=', 'done')], ['operation_id', 'delay', 'qty_produced'], ['operation_id'],
                limit=operation.time_mode_batch)
            count_data = dict((item['operation_id'][0], (item['delay'], item['qty_produced'])) for item in data)
            if count_data.get(operation.id) and count_data[operation.id][1]:
                operation.time_cycle = count_data[operation.id][0] / count_data[operation.id][1]
            else:
                operation.time_cycle = operation.time_cycle_manual

    @api.multi
    def _wo_count(self):
        # TDE CLEANME
        result = self.env['mrp.workorder'].read_group([
            ('operation_id', 'in', self.ids),
            ('state', '=', 'done')], ['operation_id'], ['operation_id'])
        mapped_data = dict([(op['operation_id'][0], op['operation_id_count']) for op in result])
        for operation in self:
            operation.wo_count = mapped_data.get(operation.id, 0)
