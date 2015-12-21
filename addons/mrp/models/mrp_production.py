# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import OrderedDict
from openerp import api, fields, models, _
from openerp.exceptions import AccessError, UserError
from openerp.tools import float_compare, float_is_zero, DEFAULT_SERVER_DATETIME_FORMAT
import openerp.addons.decimal_precision as dp
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time


class MrpProduction(models.Model):
    """
    Production Orders / Manufacturing Orders
    """
    _name = 'mrp.production'
    _description = 'Manufacturing Order'
    _date_name = 'date_planned'
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'priority desc, date_planned asc'

    def _src_id_default(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
            location.check_access_rule('read')
        except (AccessError, ValueError):
            location = False
        return location

    def _dest_id_default(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
            location.check_access_rule('read')
        except (AccessError, ValueError):
            location = False
        return location

    @api.multi
    @api.depends('move_line_ids')
    def _compute_availability(self):
        for order in self:
            if not order.move_line_ids:
                order.availability = 'none'
                continue
            assigned_list = [x.state == 'assigned' for x in order.move_line_ids] #might do partial available moves too
            if order.bom_id.ready_to_produce == 'all_available':
                if all(assigned_list):
                    order.availability = 'assigned'
                else:
                    order.availability = 'waiting'
            else:
                if all(assigned_list):
                    order.availability = 'assigned'
                    continue
                #TODO: We can skip this,but partially available is only possible when field on bom allows it
                if order.workcenter_line_ids and order.workcenter_line_ids[0].consume_line_ids:
                    if all([x.state=='assigned' for x in order.consume_line_ids]):
                        order.availability = 'partially_available'
                    else:
                        order.availability = 'waiting'
                elif any(assigned_list): #Or should be availability of first work order?
                    order.availability = 'partially_available'
                else:
                    order.availability = 'none'

    @api.multi
    def _inverse_date_planned(self):
        for order in self:
            if order.workcenter_line_ids and order.state != 'confirmed':
                raise UserError(_('You should change the Work Order planning instead!'))
            order.write({'date_planned_start_store': order.date_planned_start,
                         'date_planned_finished_store': order.date_planned_finished})

    @api.multi
    @api.depends('workcenter_line_ids.date_planned_start', 'workcenter_line_ids.date_planned_end', 'date_planned_start_store', 'date_planned_finished_store')
    def _compute_date_planned(self):
        for order in self:
            if order.workcenter_line_ids and order.state != 'confirmed': #It is already planned somehow
                first_planned_start_date = False
                last_planned_end_date = False
                for wo in order.workcenter_line_ids:
                    if wo.date_planned_start and ((not first_planned_start_date) or (fields.Datetime.from_string(wo.date_planned_start) < first_planned_start_date)):
                        first_planned_start_date = fields.Datetime.from_string(wo.date_planned_start)
                    if wo.date_planned_end and ((not last_planned_end_date) or (fields.Datetime.from_string(wo.date_planned_end) > last_planned_end_date)):
                        last_planned_end_date = fields.Datetime.from_string(wo.date_planned_end)
                order.date_planned_start = first_planned_start_date and fields.Datetime.to_string(first_planned_start_date) or False
                order.date_planned_finished = last_planned_end_date and fields.Datetime.to_string(last_planned_end_date) or False
            else:
                order.date_planned_start = order.date_planned_start_store
                order.date_planned_finished = order.date_planned_finished_store

    @api.multi
    @api.depends('workcenter_line_ids')
    def _compute_nb_orders(self):
        for mo in self:
            total_mo = 0
            done_mo = 0
            for wo in mo.workcenter_line_ids:
                total_mo += 1
                if wo.state == 'done':
                    done_mo += 1
            mo.nb_orders = total_mo
            mo.nb_done = done_mo


    name = fields.Char(string='Reference', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('mrp.production') or '/')
    origin = fields.Char(string='Source', readonly=True, states={'confirmed': [('readonly', False)]},
                         help="Reference of the document that generated this production order request.", copy=False)
    priority = fields.Selection([('0', 'Not urgent'), ('1', 'Normal'), ('2', 'Urgent'), ('3', 'Very Urgent')], 'Priority',
                                index=True, readonly=True, states=dict.fromkeys(['draft', 'confirmed'], [('readonly', False)]), default='1')
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, domain=[('type', 'in', ['product', 'consu'])])
    product_qty = fields.Float(string='Quantity to Produce', digits=dp.get_precision('Product Unit of Measure'), required=True, readonly=True, states={'confirmed': [('readonly', False)]}, default=1.0)
    product_uom_id = fields.Many2one('product.uom', string='Product Unit of Measure', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, oldname='product_uom')
    progress = fields.Float(compute='_get_progress', string='Production progress')
    location_src_id = fields.Many2one('stock.location', string='Raw Materials Location', required=True,
                                      readonly=True, states={'confirmed': [('readonly', False)]}, default=_src_id_default,
                                      help="Location where the system will look for components.")
    location_dest_id = fields.Many2one('stock.location', string='Finished Products Location', required=True,
                                       readonly=True, states={'confirmed': [('readonly', False)]}, default=_dest_id_default,
                                       help="Location where the system will stock the finished products.")
    date_planned = fields.Datetime(string='Required Date', required=True, index=True, readonly=True, states={'confirmed': [('readonly', False)]}, copy=False, default=fields.Datetime.now)
    date_planned_start_store = fields.Datetime(string='Technical Field for planned start')
    date_planned_finished_store = fields.Datetime(string='Technical Field for planned finished')
    date_planned_start = fields.Datetime(string='Scheduled Start Date', compute='_compute_date_planned', inverse='_inverse_date_planned', states={'confirmed': [('readonly', False)]}, readonly=True, store=True, index=True, copy=False)
    date_planned_finished = fields.Datetime(string='Scheduled End Date', compute='_compute_date_planned', inverse='_inverse_date_planned', states={'confirmed': [('readonly', False)]}, readonly=True, store=True, index=True, copy=False)
    date_start = fields.Datetime(string='Start Date', index=True, readonly=True, copy=False)
    date_finished = fields.Datetime(string='End Date', index=True, readonly=True, copy=False)
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material', readonly=True, states={'confirmed': [('readonly', False)]},
                             help="Bill of Materials allow you to define the list of required raw materials to make a finished product.")
    routing_id = fields.Many2one('mrp.routing', string='Routing', related = 'bom_id.routing_id', store=True,
                                 on_delete='set null', readonly=True,
                                 help="The list of operations (list of work centers) to produce the finished product. The routing is mainly used "
                                      "to compute work center costs during operations and to plan future loads on work centers based on production plannification.")
    move_prod_id = fields.Many2one('stock.move', string='Product Move', readonly=True, copy=False)
    move_line_ids = fields.One2many('stock.move', 'raw_material_production_id', string='Products to Consume',
                                    domain=[('state', 'not in', ('done', 'cancel'))], readonly=True, states={'confirmed': [('readonly', False)]}, oldname='move_lines')
    move_line_ids2 = fields.One2many('stock.move', 'raw_material_production_id', string='Consumed Products',
                                     domain=[('state', 'in', ('done', 'cancel'))], readonly=True, oldname='move_lines2')
    move_created_ids = fields.One2many('stock.move', 'production_id', string='Products to Produce',
                                       domain=[('state', 'not in', ('done', 'cancel'))], readonly=True)
    move_created_ids2 = fields.One2many('stock.move', 'production_id', 'Produced Products',
                                        domain=[('state', 'in', ('done', 'cancel'))], readonly=True)
    consume_line_ids = fields.One2many('mrp.production.consume.line', 'production_id', string='To Consume')
    workcenter_line_ids = fields.One2many('mrp.production.workcenter.line', 'production_id', string='Work Centers Utilisation',
                                          readonly=True, oldname='workcenter_lines')
    nb_orders = fields.Integer('Number of Orders', compute='_compute_nb_orders')
    nb_done = fields.Integer('Number of Orders Done', compute='_compute_nb_orders')

    state = fields.Selection([('confirmed', 'Confirmed'), ('planned', 'Planned'), ('progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Cancelled')], 'State', default='confirmed', copy=False)
    availability = fields.Selection([('assigned', 'Available'), ('partially_available', 'Partially available'), ('none', 'None'), ('waiting', 'Waiting')], compute='_compute_availability', default="none")

#     state = fields.Selection(
#         [('draft', 'New'), ('cancel', 'Cancelled'), ('confirmed', 'Awaiting Raw Materials'),
#             ('ready', 'Ready to Produce'), ('in_production', 'Production Started'), ('done', 'Done')],
#         string='Status', readonly=True, default='draft',
#         track_visibility='onchange', copy=False,
#         help="When the production order is created the status is set to 'Draft'.\n"
#              "If the order is confirmed the status is set to 'Waiting Goods.\n"
#              "If any exceptions are there, the status is set to 'Picking Exception.\n"
#              "If the stock is available then the status is set to 'Ready to Produce.\n"
#              "When the production gets started then the status is set to 'In Production.\n"
#              "When the production is over, the status is set to 'Done'.")
    hour_total = fields.Float(compute='_production_calc', string='Total Hours', store=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env['res.company']._company_default_get('mrp.production'))
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', string='Product')
    categ_id = fields.Many2one('product.category', related='product_tmpl_id.categ_id', string='Product Category', readonly=True, store=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Reference must be unique per Company!'),
    ]

    @api.multi
    @api.depends('workcenter_line_ids.hour')
    def _production_calc(self):
        """ Calculates total hours for a production order.
        :return: Dictionary of values.
        """
        data = self.env['mrp.production.workcenter.line'].read_group([('production_id', 'in', self.ids)], ['hour', 'production_id'], ['production_id'])
        mapped_data = dict([(m['production_id'][0], {'hour': m['hour']}) for m in data])
        for record in self:
            record.hour_total = mapped_data.get(record.id, {}).get('hour', 0)

    def _get_progress(self):
        """ Return product quantity percentage """
        result = dict.fromkeys(self.ids, 100)
        for mrp_production in self:
            if mrp_production.product_qty:
                done = 0.0
                for move in mrp_production.move_created_ids2:
                    if not move.scrapped and move.product_id == mrp_production.product_id:
                        done += move.product_qty
                result[mrp_production.id] = done / mrp_production.product_qty * 100
        return result

    @api.constrains('product_qty')
    def _check_qty(self):
        if self.product_qty <= 0:
            raise ValueError(_('Order quantity cannot be negative or zero!'))

    @api.model
    def create(self, values):
        if 'product_id' in values and ('product_uom_id' not in values or not values['product_uom_id']):
            values['product_uom_id'] = self.env['product.product'].browse(values.get('product_id')).uom_id.id
        production = super(MrpProduction, self).create(values)
        production.generate_moves_workorders(properties=None) #TODO: solutions for properties: procurement.property_ids
        return production

    @api.multi
    def button_plan(self):
        self.ensure_one()
        self.write({'state': 'planned'})
        #Let us try to plan the order
        self._compute_planned_workcenter(False) #TODO: should take into account existing orders

    @api.multi
    def unlink(self):
        for production in self:
            if production.state not in ('draft', 'cancel'):
                raise UserError(_('Cannot delete a manufacturing order in state \'%s\'.') % production.state)
        return super(MrpProduction, self).unlink()

    @api.onchange('location_src_id')
    def onchange_location_id(self):
        if self.location_dest_id:
            return
        if self.location_src_id:
            self.location_dest_id = self.location_src_id.id

    @api.multi
    @api.onchange('product_id', 'company_id')
    def onchange_product_id(self):
        if not self.product_id:
            self.product_uom_id = False
            self.bom_id = False
            self.routing_id = False
            self.product_tmpl_id = False
        else:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, properties=[])
            routing_id = False
            if bom_point:
                routing_id = bom_point.routing_id
            self.product_uom_id = self.product_id.uom_id.id
            self.bom_id = bom_point.id
            self.routing_id = routing_id.id
            self.product_tmpl_id = self.product_id.product_tmpl_id.id
            self.date_planned_start = fields.Datetime.to_string(datetime.now())
            date_planned = datetime.now() + relativedelta(days=self.product_id.produce_delay or 0.0) + relativedelta(days=self.company_id.manufacturing_lead)
            self.date_planned = fields.Datetime.to_string(date_planned)
            self.date_planned_finished = date_planned
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}}

    @api.onchange('bom_id')
    def onchange_bom_id(self):
        if not self.bom_id:
            self.routing_id = False
        self.routing_id = self.bom_id.routing_id.id or False

    def _prepare_lines(self, properties=None):
        # search BoM structure and route
        bom_point = self.bom_id
        if not bom_point:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, properties=properties)
            if bom_point:
                self.write({'bom_id': bom_point.id, 'routing_id': bom_point.routing_id and bom_point.routing_id.id or False})

        if not bom_point:
            raise UserError(_("Cannot find a bill of material for this product."))

        # get components and workcenter_line_ids from BoM structure
        factor = self.product_uom_id._compute_qty(self.product_qty, bom_point.product_uom_id.id)
        # product_line_ids, workcenter_line_ids
        return bom_point.explode(self.product_id, factor / bom_point.product_qty, properties=properties, routing_id=self.routing_id.id)

    @api.multi
    def _compute_planned_workcenter(self, mini=False):
        """ Computes planned and finished dates for work order.
        @return: Calculated date
        """
        dt_end = datetime.now()
        context = self.env.context or {}
        for po in self: #Maybe need to make difference between different pos
            dt_end = datetime.strptime(po.date_planned_start, '%Y-%m-%d %H:%M:%S')
            old = None
            for wci in range(len(po.workcenter_line_ids)):
                wc  = po.workcenter_line_ids[wci]
                if (old is None) or (wc.sequence>old):
                    dt = dt_end
                if context.get('__last_update'):
                    del context['__last_update']
                if (wc.date_planned_start < dt.strftime('%Y-%m-%d %H:%M:%S')) or mini:
                    wc.write({
                        'date_planned_start': dt.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    i = wc.workcenter_id.calendar_id.interval_get(dt, wc.hour)
                    if i:
                        i = i[0]
                        dt_end = max(dt_end, i[-1][1])
                else:
                    dt_end = datetime.strptime(wc.date_planned_end, '%Y-%m-%d %H:%M:%S')
                if dt_end:
                    wc.write({'date_planned_end': dt_end.strftime('%Y-%m-%d %H:%M:%S')})
                old = wc.sequence or 0
        return dt_end

    @api.multi
    def action_cancel(self):
        """ Cancels the production order and related stock moves.
        :return: True
        """
        ProcurementOrder = self.env['procurement.order']
        for production in self:
            if production.move_created_ids:
                production.move_created_ids.action_cancel()
            procs = ProcurementOrder.search([('move_dest_id', 'in', [record.id for record in production.move_line_ids])])
            if procs:
                procs.cancel()
            production.move_line_ids.action_cancel()
        self.write({'state': 'cancel'})
        # Put related procurements in exception
        procs = ProcurementOrder.search([('production_id', 'in', [self.ids])])
        if procs:
            procs.message_post(body=_('Manufacturing order cancelled.'))
            procs.write({'state': 'exception'})
        return True

    @api.multi
    def generate_production_consume_lines(self):
        """ Changes the production state to Ready and location id of stock move.
        :return: True
        """
        consume_obj = self.env['mrp.production.consume.line']
        for production in self:
            #Let us create consume lines
            consume_lines = production._calculate_qty()
            for line in consume_lines:
                line['production_id'] = production.id
                consume_obj.create(line)
            if production.move_prod_id and production.move_prod_id.location_id.id != production.location_dest_id.id:
                production.move_prod_id.write({'location_id': production.location_dest_id.id})
        return True

    @api.multi
    def action_production_end(self):
        """ Changes production state to Finish and writes finished date.
        :return: True
        """
        self._costs_generate()
        write_res = self.write({'state': 'done', 'date_finished': fields.datetime.now()})
        # Check related procurements
        self.env["procurement.order"].search([('production_id', 'in', self.ids)]).check()
        return write_res

    def _get_subproduct_factor(self, move=None):
        """ Compute the factor to compute the qty of procucts to produce for the given production_id. By default,
            it's always equal to the quantity encoded in the production order or the production wizard, but if the
            module mrp_subproduct is installed, then we must use the move_id to identify the product to produce
            and its quantity.
        :param production_id: ID of the mrp.order
        :param move_id: ID of the stock move that needs to be produced. Will be used in mrp_subproduct.
        :return: The factor to apply to the quantity that we should produce for the given production order.
        """
        return 1

    def _get_produced_qty(self):
        ''' returns the produced quantity of product 'production.product_id' for the given production, in the product UoM
        '''
        produced_qty = 0
        for produced_product in self.move_created_ids2:
            if (produced_product.scrapped) or (produced_product.product_id.id != self.product_id.id):
                continue
            produced_qty += produced_product.product_qty
        return produced_qty


    def _calculate_qty(self, to_produce_qty=0.0): #Add option to put them partially or not at all
        self.ensure_one()
        consume_dict = {}
        for move in self.move_line_ids:
            if move.reserved_quant_ids:
                for quant in move.reserved_quant_ids:
                    key = (move.workorder_id.id, move.product_id.id, quant.lot_id.id, move.product_uom.id)
                    consume_dict.setdefault(key, 0.0)
                    consume_dict[key] += quant.qty
            elif move.state == 'assigned':
                key = (move.workorder_id.id, move.product_id.id, False, move.product_uom.id)
                consume_dict.setdefault(key, 0.0)
                consume_dict[key] += move.product_qty
        consume_lines=[]
        for key in consume_dict:
            consume_lines.append({'product_id': key[1], 'product_qty': consume_dict[key], 'production_lot_ids': key[2], 'workorder_id': key[0], 'product_uom_id': key[3]})
        return consume_lines

    @api.multi
    def action_produce(self, production_qty, production_mode, wizard=False):
        """ To produce final product based on production mode (consume/consume&produce).
        If Production mode is consume, all stock move lines of raw materials will be done/consumed.
        If Production mode is consume & produce, all stock move lines of raw materials will be done/consumed
        and stock move lines of final product will be also done/produced.
        :param production_qty: specify qty to produce in the uom of the production order
        :param production_mode: specify production mode (consume/consume&produce).
        :param wizard: the mrp produce product wizard, which will tell the amount of consumed products needed
        :return: True
        """
        self.ensure_one()

        ProductProduct = self.env['product.product']
        production_qty_uom = self.product_uom_id._compute_qty(production_qty, self.product_id.uom_id.id)
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        main_production_move = False
        if production_mode == 'consume_produce':
            # To produce remaining qty of final product
            produced_products = {}
            for produced_product in self.move_created_ids2:
                if produced_product.scrapped:
                    continue
                if not produced_products.get(produced_product.product_id.id, False):
                    produced_products[produced_product.product_id.id] = 0
                produced_products[produced_product.product_id.id] += produced_product.product_qty
            for produce_product in self.move_created_ids:
                subproduct_factor = self._get_subproduct_factor(produce_product)
                lot_id = False
                if wizard:
                    lot_id = wizard.lot_id.id
                qty = min(subproduct_factor * production_qty_uom, produce_product.product_qty)  # Needed when producing more than maximum quantity
                new_moves = produce_product.action_consume(qty, location_id=produce_product.location_id.id, restrict_lot_id=lot_id)
                new_moves.write({'production_id': self.id})
                remaining_qty = subproduct_factor * production_qty_uom - qty
                if not float_is_zero(remaining_qty, precision_digits=precision):
                    # In case you need to make more than planned
                    # consumed more in wizard than previously planned
                    extra_move_id = produce_product.copy(default={'product_uom_qty': remaining_qty, 'production_id': self.id})
                    extra_move_id.action_confirm()
                    extra_move_id.action_done()

                if produce_product.product_id.id == self.product_id.id:
                    main_production_move = produce_product.id

        if production_mode in ['consume', 'consume_produce']:
            if wizard:
                consume_lines = []
                for cons in self.consume_line_ids:
                    if cons.qty_done > 0.0:
                        consume_lines.append({'product_id': cons.product_id.id, 'production_lot_ids': cons.production_lot_ids.ids, 'product_qty': cons.qty_done})
            else:
                consume_lines = self._calculate_qty(production_qty_uom)
            for consume in consume_lines:
                remaining_qty = consume['product_qty']
                for raw_material_line in self.move_line_ids:
                    if raw_material_line.state in ('done', 'cancel'):
                        continue
                    if remaining_qty <= 0:
                        break
                    if consume['product_id'] != raw_material_line.product_id.id:
                        continue
                    consumed_qty = min(remaining_qty, raw_material_line.product_qty)
                    raw_material_line.action_consume(consumed_qty, raw_material_line.location_id.id,
                                                     restrict_lot_id=consume['lot_id'], consumed_for_id=main_production_move)
                    remaining_qty -= consumed_qty
                if not float_is_zero(remaining_qty, precision_digits=precision):
                    # consumed more in wizard than previously planned
                    product = ProductProduct.browse(consume['product_id'])
                    extra_move_id = self.env['stock.move'].create({'product_id': consume['product_id'],
                                                                   'product_uom_qty': consume['product_qty'],
                                                                   'product_uom': product.uom_id.id,
                                                                   'name': _('Extra'),
                                                                   'restrict_lot_id': consume['lot_id'], 
                                                                   'consumed_for_id': main_production_move, 
                                                                   'procure_method': 'make_to_stock',
                                                                   'raw_material_production_id': self.id,
                                                                   'location_id': self.location_src_id.id,
                                                                   'location_dest_id': product.property_stock_production.id,
                                                                   })
                    extra_move_id.action_confirm()
                    extra_move_id.action_done()

        self.message_post(body=_("%s produced") % self._description)

        # Remove remaining products to consume if no more products to produce
        if not self.move_created_ids and self.move_line_ids:
            self.move_line_ids.action_cancel()

        return True 

    def _make_production_produce_line(self):
        procs = self.env['procurement.order'].search([('production_id', '=', self.id)])
        procurement = procs and procs[0]
        data = {
            'name': self.name,
            'date': self.date_planned,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'location_id': self.product_id.property_stock_production.id,
            'location_dest_id': self.location_dest_id.id,
            'move_dest_id': self.move_prod_id.id,
            'procurement_id': procurement and procurement.id,
            'company_id': self.company_id.id,
            'production_id': self.id,
            'origin': self.name,
            'group_id': procurement and procurement.group_id.id,
        }
        move_id = self.env['stock.move'].create(data)
        # a phantom bom cannot be used in mrp order so it's ok to assume the list returned by action_confirm
        # is 1 element long, so we can take the first.
        return move_id.action_confirm()[0]

    def _get_raw_material_procure_method(self, product, location=False, location_dest=False):
        '''This method returns the procure_method to use when creating the stock move for the production raw materials
        Besides the standard configuration of looking if the product or product category has the MTO route,
        you can also define a rule e.g. from Stock to Production (which might be used in the future like the sale orders)
        '''
        routes = product.route_ids + product.categ_id.total_route_ids

        if location and location_dest:
            pull = self.env['procurement.rule'].search([('route_id', 'in', routes.ids),
                                                        ('location_id', '=', location_dest.id),
                                                        ('location_src_id', '=', location.id)], limit=1)
            if pull:
                return pull.procure_method

        try:
            mto_route = self.env['stock.warehouse']._get_mto_route()
        except:
            return "make_to_stock"

        if mto_route in routes.ids:
            return "make_to_order"
        return "make_to_stock"

    def _create_previous_move(self, move, source_location, dest_location):
        '''
        When the routing gives a different location than the raw material location of the production order,
        we should create an extra move from the raw material location to the location of the routing, which
        precedes the consumption line (chained).  The picking type depends on the warehouse in which this happens
        and the type of locations.
        '''
        # Need to search for a picking type
        code = move.get_code_from_locs(source_location, dest_location)
        if code == 'outgoing':
            check_loc = source_location
        else:
            check_loc = dest_location
        warehouse = check_loc.get_warehouse()
        domain = [('code', '=', code)]
        if warehouse:
            domain += [('warehouse_id', '=', warehouse)]
        types = self.env['stock.picking.type'].search(domain)
        move = move.copy(default={
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'procure_method': self._get_raw_material_procure_method(move.product_id, location=source_location,
                                                                    location_dest=dest_location),
            'raw_material_production_id': False,
            'move_dest_id': move.id,
            'picking_type_id': types and types[0] or False,
        })
        return move


    def _prepare_consume_line(self, line, source_location, prev_move):
        """
            Prepare consume lines based on BoM 
        """
        self.ensure_one()
        product = self.env['product.product'].browse(line['product_id'])
        WorkOrder = self.env['mrp.production.workcenter.line']
        destination_location = self.product_id.property_stock_production
        vals = {
            'name': self.name,
            'date': self.date_planned,
            'product_id': product.id,
            'product_uom_qty': line['product_uom_qty'],
            'product_uom': line['product_uom_id'],
            'location_id': source_location.id,
            'location_dest_id': destination_location.id,
            'company_id': self.company_id.id,
            'procure_method': prev_move and 'make_to_stock' or self._get_raw_material_procure_method(product, location=source_location,
                                                                                                     location_dest=destination_location),  # Make_to_stock avoids creating procurement
            'raw_material_production_id': self.id,
            'price_unit': product.standard_price,
            'origin': self.name,
            'warehouse_id': self.location_src_id.get_warehouse(),
            'group_id': self.move_prod_id.group_id.id,
            'operation_id': line['operation_id'],
            'workorder_id' : WorkOrder.search([('operation_id', '=', line['operation_id']), ('production_id', '=', self.id)], limit=1).id,
        }
        return vals

    @api.multi
    def generate_moves_workorders(self, properties=None):
        """ 
            Generates moves and work orders
        """
        WorkOrder = self.env['mrp.production.workcenter.line']
        
        for production in self:
            #Produce lines
            production._make_production_produce_line()
            
            #Consume lines
            results, results2 = production._prepare_lines(properties=properties)
            for line in results2:
                line['production_id'] = production.id
                WorkOrder.create(line)
            
            stock_moves = self.env['stock.move']
            source_location = production.location_src_id
            prev_move = False
            prod_location=source_location
            if production.bom_id.routing_id and production.bom_id.routing_id.location_id and self.bom_id.routing_id.location_id != source_location:
                source_location = production.bom_id.routing_id.location_id
                prev_move=True
            for line in results:
                product = self.env['product.product'].browse(line['product_id'])
                if product.type in ['product', 'consu']:
                    stock_move_vals = production._prepare_consume_line(line, source_location, prev_move)
                    stock_move_vals['production_id'] = production.id
                    stock_move = self.env['stock.move'].create(stock_move_vals)
                    stock_moves = stock_moves | stock_move
                    if prev_move:
                        prev_move = self._create_previous_move(stock_move, prod_location, source_location)
                        stock_moves = stock_moves | prev_move
            if stock_moves:
                stock_moves.action_confirm()
        return 0


    @api.multi
    def action_assign(self):
        """
        Checks the availability on the consume lines of the production order
        """
        for production in self:
            production.move_line_ids.action_assign()
            if production.availability in ('assigned', 'partially_available'):
                production.generate_production_consume_lines()
        return True
 
    @api.multi
    def force_assign(self):
        for order in self:
            order.move_line_ids.force_assign()
            order.generate_production_consume_lines()
        return True


class MrpProductionWorkcenterLine(models.Model):
    _name = 'mrp.production.workcenter.line'
    _description = 'Work Order'
    _order = 'sequence'
    _inherit = ['mail.thread']

    @api.multi
    @api.depends('time_ids')
    def _compute_started(self):
        for workorder in self:
            running = [x.date_start for x in workorder.time_ids if x.state == 'running']
            if running:
                workorder.started_since = running[0]

    @api.multi
    @api.depends('time_ids')
    def _compute_delay(self):
        for workorder in self:
            workorder.delay = sum([x.duration for x in workorder.time_ids if x.state == "done"])

    @api.multi
    @api.depends('consume_line_ids')
    def _compute_availability(self):
        for workorder in self:
            if workorder.consume_line_ids:
                if any([x.state != 'assigned' for x in workorder.move_line_ids if not x.scrapped]):
                    workorder.availability = 'waiting'
                else:
                    workorder.availability = 'assigned'
            else:
                workorder.availability = workorder.production_id.availability == 'assigned' and 'assigned' or 'waiting'

    name = fields.Char(string='Work Order', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center', required=True)
    hour = fields.Float(string='Expected Duration', digits=(16, 2))
    sequence = fields.Integer(required=True, default=1, help="Gives the sequence order when displaying a list of work orders.")
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', track_visibility='onchange', index=True, ondelete='cascade', required=True)
    state = fields.Selection([('confirmed', 'Confirmed'), ('ready', 'Ready'), ('cancel', 'Cancelled'), ('pause', 'Pending'), ('progress', 'In Progress'), ('done', 'Finished')], default='confirmed')
    date_planned_start = fields.Datetime('Scheduled Date Start')
    date_planned_end = fields.Datetime('Scheduled Date Finished')
    date_start = fields.Datetime('Effective Start Date')
    date_finished = fields.Datetime('Effective End Date')
    delay = fields.Float('Real Duration', compute='_compute_delay', readonly=True)
    qty_produced = fields.Float('Qty Produced', help="The number of products already handled by this work order", default=0.0) #TODO: decimal precision
    operation_id = fields.Many2one('mrp.routing.workcenter', 'Operation') #Should be used differently as BoM can change in the meantime
    move_line_ids = fields.One2many('stock.move', 'workorder_id', 'Moves')
    consume_line_ids = fields.One2many('mrp.production.consume.line', 'workorder_id')
    availability = fields.Selection([('waiting', 'Waiting'), ('assigned', 'Available')], 'Stock Availability', store=True, compute='_compute_availability')
    production_state = fields.Selection(related='production_id.state', readonly=True)
    product = fields.Many2one('product.product', related='production_id.product_id', string="Product", readonly=True)
    qty = fields.Float(related='production_id.product_qty', string='Qty', readonly=True, store=True) #store really needed?
    uom = fields.Many2one('product.uom', related='production_id.product_uom_id', string='Unit of Measure')
    started_since = fields.Datetime('Started Since', compute='_compute_started')
    time_ids = fields.One2many('mrp.production.workcenter.line.time', 'workorder_id')
    worksheet = fields.Binary('Worksheet', related='operation_id.worksheet')
    
    @api.multi
    def button_draft(self):
        self.write({'state': 'confirmed'})

    @api.multi
    def button_plan(self):
        self.write({'state' 'planned'})

    @api.multi
    def button_start(self):
        timeline = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            if workorder.production_id.state != 'progress':
                workorder.production_id.state = 'progress'
            timeline.create({'workorder_id': workorder.id,
                             'state': 'running',
                             'date_start': datetime.now(),
                             'user_id': self.env.user.id})
        self.write({'state': 'progress',
                    'date_start': datetime.now(),
                    })
        
    @api.multi
    def end_previous(self):
        timeline_obj = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            timeline = timeline_obj.search([('workorder_id', '=', workorder.id), ('state', '=', 'running')], limit=1)
            timed = datetime.now() - fields.Datetime.from_string(timeline.date_start)
            hours = timed.total_seconds() / 3600.0
            timeline.write({'state': 'done',
                            'duration': hours})

    @api.multi
    def button_resume(self):
        timeline_obj = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            timeline = timeline_obj.create({'workorder_id': workorder.id,
                                            'state': 'running',
                                            'date_start': datetime.now(),
                                            'user_id': self.env.user.id})
        self.write({'state':'progress'})

    @api.multi
    def button_pause(self):
        self.end_previous()
        self.write({'state': 'pause'})

    @api.multi
    def button_cancel(self):
        self.write({'state': 'cancel'})

    @api.multi
    def button_done(self):
        self.end_previous()
        self.write({'state': 'done',
                    'date_finished': datetime.now()})


class MrpProductionWorkcenterLineTime(models.Model):
    _name='mrp.production.workcenter.line.time'
    _description = 'Work Order Timesheet Line'
    
    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
    date_start = fields.Datetime('Start Date')
    duration = fields.Float('Duration')
    user_id = fields.Many2one('res.users', string="User")
    state = fields.Selection([('running', 'Running'), ('done', 'Done')], string="Status", default="running")


class MrpProductionConsumeLine(models.Model):
    _name = "mrp.production.consume.line"
    _description = "Consume Lines"

    product_id = fields.Many2one('product.product', string='Product')
    product_uom_id = fields.Many2one('product.uom', string='Unit of Measure')
    product_qty = fields.Float(string='Quantity to Consume', digits=dp.get_precision('Product Unit of Measure'))
    production_lot_ids = fields.One2many('production.operation.lot', 'operation_id', string='Related Packing Operations')
    qty_done = fields.Float(string='Quantity Consumed', digits=dp.get_precision('Product Unit of Measure'))
    production_id = fields.Many2one('mrp.production', string='Production Order')
    workorder_id = fields.Many2one('mrp.production.workcenter.line', string='Work Order')
    lots_visible = fields.Boolean(compute='_compute_lots_visible')

    @api.multi
    def _compute_lots_visible(self):
        for consume_line in self:
            if consume_line.production_lot_ids:
                consume_line.lots_visible = True
                continue
            consume_line.lots_visible = (consume_line.product_id.tracking != 'none')

    @api.multi
    def save(self):
        for pack in self:
            if pack.product_id.tracking != 'none':
                qty_done = sum([x.qty for x in pack.production_lot_ids])
                pack.qty_done = qty_done
        return {'type': 'ir.actions.act_window_close'}

    @api.multi
    def split_lot(self):
        self.ensure_one()
        ctx = {}
        serial = (self.product_id.tracking == 'serial')
        view = self.env.ref('mrp.mrp_production_consume_line_lot_form').id
        show_reserved = any([x for x in self.production_lot_ids if x.qty_todo > 0.0])
        ctx.update({'serial': serial,
                    'show_reserved': show_reserved,})
        return {
            'name': _('Lot Details'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.production.consume.line',
            'views': [(view, 'form')],
            'view_id': view,
            'target': 'new',
            'res_id': self.id,
            'context': ctx,
        }


class ProductionOperationLot(models.Model):
    _name = "production.operation.lot"
    _description = "Specifies lot/serial number for production operations that need it"

    @api.multi
    def _get_plus(self):
        for operation in self:
            operation.plus_visible = True
            if operation.operation_id.product_id.tracking == 'serial':
                operation.plus_visible = (operation.qty == 0.0)
            else:
                operation.plus_visible = (operation.qty_todo == 0.0) or (operation.qty < operation.qty_todo)

    operation_id = fields.Many2one('mrp.production.consume.line')
    qty = fields.Float(string='Done', default=1)
    lot_id = fields.Many2one('stock.production.lot', string='Lot/Serial Number')
    lot_name = fields.Char(string='Lot Name')
    qty_todo = fields.Float(string='To Do', default=0.0)
    plus_visible = fields.Boolean(compute=_get_plus)

    @api.constrains('lot_id', 'lot_name')
    def _check_lot(self):
        for packlot in self:
            if not packlot.lot_name and not packlot.lot_id:
                raise UserError(_('Lot name and lot id required ..'))
        return True

    _sql_constraints = [
        ('qty', 'CHECK(qty >= 0.0)','Quantity must be greater than or equal to 0.0!'),
        ('uniq_lot_id', 'unique(operation_id, lot_id)', 'You have already mentioned this lot in another line'),
        ('uniq_lot_name', 'unique(operation_id, lot_name)', 'You have already mentioned this lot name in another line')]

    # @api.multi
    # def do_plus(self):
    #     self.ensure_one()
    #     self.qty += 1
    #     self.operation_id.qty_done = sum([x.qty for x in self.operation_id.production_lot_ids])
    #     return self.operation_id.split_lot()

    # @api.multi
    # def do_minus(self):
    #     self.ensure_one()
    #     self.qty -= 1
    #     self.operation_id.qty_done = sum([x.qty for x in self.operation_id.production_lot_ids])
    #     return self.operation_id.split_lot()
    
    
class MrpUnbuild(models.Model):
    _name = "mrp.unbuild"
    _description = "Unbuild Order"
    
    name = fields.Char(string='Reference', required=True, readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('mrp.unbuild') or '/')
    product_id = fields.Many2one('product.product', string="Product")
    product_qty = fields.Float('Product Quantity')
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material') #Add domain
    lot_id = fields.Many2one('stock.production.lot', 'Lot')
    location_id = fields.Many2one('stock.location', 'Location')
    consume_line_id = fields.Many2one('stock.move', readonly=True)
    produce_line_ids = fields.One2many('stock.move', 'unbuild_id', readonly=True)
    state = fields.Selection([('confirmed', 'Confirmed'), ('done', 'Done')], "State")
    
    #TODO: need quants defined here
    
